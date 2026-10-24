"""Comprehensive tests for institution management and administrative role isolation."""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.main import app
from app.models.user import User, UserRole


async def _create_user_and_token(client: AsyncClient, email: str, role: UserRole, name: str) -> str:
    """Helper to create a user with a specific role and return an access token."""
    response = await client.post(
        "/api/auth/register",
        json={
            "email": email,
            "password": "password1234",
            "full_name": name,
            "role": "student",
        },
    )
    assert response.status_code == 201, response.text
    if role != UserRole.STUDENT:
        database = app.state.test_db_session
        account = (await database.execute(select(User).where(User.email == email))).scalar_one()
        account.role = role
        await database.commit()
    return response.json()["access_token"]


@pytest.mark.asyncio
async def test_platform_admin_can_create_and_list_institutions(client: AsyncClient) -> None:
    """Platform Admin can create institutions and list them; duplicates are rejected."""
    admin_token = await _create_user_and_token(
        client, "platform_admin@viva.edu", UserRole.ADMIN, "Platform Admin"
    )
    h_admin = {"Authorization": f"Bearer {admin_token}"}

    # 1. Create first institution
    res1 = await client.post(
        "/api/admin/institutions",
        headers=h_admin,
        json={"name": "St. Xavier's University", "code": "SXU"},
    )
    assert res1.status_code == 201
    inst1 = res1.json()
    assert inst1["name"] == "St. Xavier's University"
    assert inst1["code"] == "SXU"
    assert inst1["is_active"] is True
    assert "id" in inst1

    # 2. Create second institution
    res2 = await client.post(
        "/api/admin/institutions",
        headers=h_admin,
        json={"name": "Trinity Institute of Tech", "code": "TIT"},
    )
    assert res2.status_code == 201
    inst2 = res2.json()
    assert inst2["code"] == "TIT"

    # 3. Duplicate name or code rejected with 409 Conflict
    dup_name = await client.post(
        "/api/admin/institutions",
        headers=h_admin,
        json={"name": "St. Xavier's University", "code": "DIFFERENT"},
    )
    assert dup_name.status_code == 409

    dup_code = await client.post(
        "/api/admin/institutions",
        headers=h_admin,
        json={"name": "Different Name", "code": "SXU"},
    )
    assert dup_code.status_code == 409

    # 4. List institutions returns both
    list_res = await client.get("/api/admin/institutions", headers=h_admin)
    assert list_res.status_code == 200
    institutions = list_res.json()
    assert len(institutions) >= 2
    codes = {item["code"] for item in institutions}
    assert "SXU" in codes
    assert "TIT" in codes


@pytest.mark.asyncio
async def test_non_admin_cannot_manage_institutions(client: AsyncClient) -> None:
    """Teachers, students, and unauthenticated requests are forbidden from institution administration."""
    teacher_token = await _create_user_and_token(
        client, "t_no_inst@viva.edu", UserRole.TEACHER, "Teacher"
    )
    student_token = await _create_user_and_token(
        client, "s_no_inst@viva.edu", UserRole.STUDENT, "Student"
    )

    h_teacher = {"Authorization": f"Bearer {teacher_token}"}
    h_student = {"Authorization": f"Bearer {student_token}"}

    payload = {"name": "Unauthorized College", "code": "UNAUTH"}

    # Unauthenticated -> 401
    assert (await client.post("/api/admin/institutions", json=payload)).status_code == 401
    assert (await client.get("/api/admin/institutions")).status_code == 401

    # Teacher -> 403
    assert (
        await client.post("/api/admin/institutions", headers=h_teacher, json=payload)
    ).status_code == 403
    assert (await client.get("/api/admin/institutions", headers=h_teacher)).status_code == 403

    # Student -> 403
    assert (
        await client.post("/api/admin/institutions", headers=h_student, json=payload)
    ).status_code == 403
    assert (await client.get("/api/admin/institutions", headers=h_student)).status_code == 403


@pytest.mark.asyncio
async def test_platform_admin_can_appoint_institution_admin(client: AsyncClient) -> None:
    """Platform Admin can appoint an institution admin bound to an existing institution."""
    admin_token = await _create_user_and_token(
        client, "sysadmin_inst@viva.edu", UserRole.ADMIN, "System Admin"
    )
    h_admin = {"Authorization": f"Bearer {admin_token}"}

    inst_res = await client.post(
        "/api/admin/institutions",
        headers=h_admin,
        json={"name": "Apex Engineering College", "code": "AEC"},
    )
    assert inst_res.status_code == 201
    inst_id = inst_res.json()["id"]

    # 1. Appoint institution admin
    appoint_res = await client.post(
        f"/api/admin/institutions/{inst_id}/admins",
        headers=h_admin,
        json={
            "email": "dean_apex@apex.edu",
            "password": "secureDeanPass123",
            "full_name": "Dean Robert",
        },
    )
    assert appoint_res.status_code == 201
    inst_admin = appoint_res.json()
    assert inst_admin["email"] == "dean_apex@apex.edu"
    assert inst_admin["role"] == "institution_admin"
    assert inst_admin["institution_id"] == inst_id
    assert "password" not in inst_admin

    # Verify password was hashed in database
    db = app.state.test_db_session
    user_db = (
        await db.execute(select(User).where(User.email == "dean_apex@apex.edu"))
    ).scalar_one()
    assert user_db.hashed_password != "secureDeanPass123"
    assert user_db.role == UserRole.INSTITUTION_ADMIN
    assert str(user_db.institution_id) == inst_id

    # 2. Duplicate email rejected with 409
    dup_res = await client.post(
        f"/api/admin/institutions/{inst_id}/admins",
        headers=h_admin,
        json={
            "email": "dean_apex@apex.edu",
            "password": "anotherPassword123",
            "full_name": "Dean Copy",
        },
    )
    assert dup_res.status_code == 409

    # 3. Missing institution returns 404
    missing_id = str(uuid.uuid4())
    assert (
        await client.post(
            f"/api/admin/institutions/{missing_id}/admins",
            headers=h_admin,
            json={
                "email": "ghost@apex.edu",
                "password": "pass123456",
                "full_name": "Ghost",
            },
        )
    ).status_code == 404


@pytest.mark.asyncio
async def test_institution_admin_cannot_access_platform_admin_endpoints(
    client: AsyncClient,
) -> None:
    """An appointed institution admin cannot perform platform-level administration."""
    admin_token = await _create_user_and_token(
        client, "head_admin@viva.edu", UserRole.ADMIN, "Head Admin"
    )
    h_admin = {"Authorization": f"Bearer {admin_token}"}

    inst_res = await client.post(
        "/api/admin/institutions",
        headers=h_admin,
        json={"name": "Pioneer University", "code": "PU"},
    )
    inst_id = inst_res.json()["id"]

    appoint_res = await client.post(
        f"/api/admin/institutions/{inst_id}/admins",
        headers=h_admin,
        json={
            "email": "provost@pioneer.edu",
            "password": "provostPass123",
            "full_name": "Provost Elena",
        },
    )
    assert appoint_res.status_code == 201

    # Login as Institution Admin
    login_res = await client.post(
        "/api/auth/login",
        json={"email": "provost@pioneer.edu", "password": "provostPass123"},
    )
    assert login_res.status_code == 200
    inst_admin_token = login_res.json()["access_token"]
    h_inst_admin = {"Authorization": f"Bearer {inst_admin_token}"}

    # Institution admin cannot create new institutions
    assert (
        await client.post(
            "/api/admin/institutions",
            headers=h_inst_admin,
            json={"name": "Hijacked College", "code": "HIJACK"},
        )
    ).status_code == 403

    # Institution admin cannot list platform institutions
    assert (await client.get("/api/admin/institutions", headers=h_inst_admin)).status_code == 403

    # Institution admin cannot appoint other institution admins
    assert (
        await client.post(
            f"/api/admin/institutions/{inst_id}/admins",
            headers=h_inst_admin,
            json={
                "email": "sub_admin@pioneer.edu",
                "password": "password123",
                "full_name": "Sub Admin",
            },
        )
    ).status_code == 403


@pytest.mark.asyncio
async def test_existing_independent_users_preserved(client: AsyncClient) -> None:
    """Independent students and teachers without institutions have institution_id: None and function normally."""
    t_token = await _create_user_and_token(
        client, "indep_teacher@viva.edu", UserRole.TEACHER, "Independent Teacher"
    )
    s_token = await _create_user_and_token(
        client, "indep_student@viva.edu", UserRole.STUDENT, "Independent Student"
    )

    # Verify /api/auth/me returns institution_id as None
    me_t = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {t_token}"})
    assert me_t.status_code == 200
    assert me_t.json()["institution_id"] is None

    me_s = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {s_token}"})
    assert me_s.status_code == 200
    assert me_s.json()["institution_id"] is None

    # Independent teacher can create courses as before
    course_res = await client.post(
        "/api/courses",
        headers={"Authorization": f"Bearer {t_token}"},
        json={"name": "Independent Physics", "code": "PHY101", "description": "Mechanics"},
    )
    assert course_res.status_code == 201


@pytest.mark.asyncio
async def test_institution_admin_can_create_and_list_teachers(client: AsyncClient) -> None:
    """An institution admin can create and list teachers belonging strictly to their institution."""
    admin_token = await _create_user_and_token(
        client, "super_admin@viva.edu", UserRole.ADMIN, "Super Admin"
    )
    h_admin = {"Authorization": f"Bearer {admin_token}"}

    # 1. Platform Admin creates institution and appoints institution admin
    inst_res = await client.post(
        "/api/admin/institutions",
        headers=h_admin,
        json={"name": "Imperial College", "code": "IC"},
    )
    inst_id = inst_res.json()["id"]

    await client.post(
        f"/api/admin/institutions/{inst_id}/admins",
        headers=h_admin,
        json={
            "email": "dean_ic@imperial.edu",
            "password": "deanPassword123",
            "full_name": "Dean Arthur",
        },
    )

    # 2. Login as Institution Admin
    login_res = await client.post(
        "/api/auth/login",
        json={"email": "dean_ic@imperial.edu", "password": "deanPassword123"},
    )
    inst_admin_token = login_res.json()["access_token"]
    h_inst_admin = {"Authorization": f"Bearer {inst_admin_token}"}

    # 3. Create teacher 1
    t1_res = await client.post(
        "/api/institution/teachers",
        headers=h_inst_admin,
        json={
            "email": "prof_turing@imperial.edu",
            "password": "turingPass123",
            "full_name": "Alan Turing",
        },
    )
    assert t1_res.status_code == 201
    t1 = t1_res.json()
    assert t1["email"] == "prof_turing@imperial.edu"
    assert t1["full_name"] == "Alan Turing"
    assert t1["role"] == "teacher"
    assert t1["institution_id"] == inst_id
    assert "password" not in t1
    assert "hashed_password" not in t1

    # 4. Create teacher 2
    t2_res = await client.post(
        "/api/institution/teachers",
        headers=h_inst_admin,
        json={
            "email": "prof_lovelace@imperial.edu",
            "password": "lovelacePass123",
            "full_name": "Ada Lovelace",
        },
    )
    assert t2_res.status_code == 201
    t2 = t2_res.json()
    assert t2["role"] == "teacher"
    assert t2["institution_id"] == inst_id

    # 5. List teachers
    list_res = await client.get("/api/institution/teachers", headers=h_inst_admin)
    assert list_res.status_code == 200
    teachers = list_res.json()
    assert len(teachers) == 2
    emails = {item["email"] for item in teachers}
    assert "prof_turing@imperial.edu" in emails
    assert "prof_lovelace@imperial.edu" in emails


@pytest.mark.asyncio
async def test_cross_institution_teacher_isolation(client: AsyncClient) -> None:
    """Institution A cannot list or view teachers belonging to Institution B."""
    admin_token = await _create_user_and_token(
        client, "root_admin@viva.edu", UserRole.ADMIN, "Root Admin"
    )
    h_admin = {"Authorization": f"Bearer {admin_token}"}

    # Setup Institution A
    inst_a = (
        await client.post(
            "/api/admin/institutions", headers=h_admin, json={"name": "College Alpha", "code": "CA"}
        )
    ).json()
    await client.post(
        f"/api/admin/institutions/{inst_a['id']}/admins",
        headers=h_admin,
        json={"email": "admin_a@alpha.edu", "password": "passA1234", "full_name": "Admin Alpha"},
    )
    token_a = (
        await client.post(
            "/api/auth/login", json={"email": "admin_a@alpha.edu", "password": "passA1234"}
        )
    ).json()["access_token"]
    h_a = {"Authorization": f"Bearer {token_a}"}

    # Setup Institution B
    inst_b = (
        await client.post(
            "/api/admin/institutions", headers=h_admin, json={"name": "College Beta", "code": "CB"}
        )
    ).json()
    await client.post(
        f"/api/admin/institutions/{inst_b['id']}/admins",
        headers=h_admin,
        json={"email": "admin_b@beta.edu", "password": "passB1234", "full_name": "Admin Beta"},
    )
    token_b = (
        await client.post(
            "/api/auth/login", json={"email": "admin_b@beta.edu", "password": "passB1234"}
        )
    ).json()["access_token"]
    h_b = {"Authorization": f"Bearer {token_b}"}

    # Admin A creates Teacher A
    res_ta = await client.post(
        "/api/institution/teachers",
        headers=h_a,
        json={
            "email": "teacher_a@alpha.edu",
            "password": "teacherPassA1",
            "full_name": "Teacher Alpha",
        },
    )
    assert res_ta.status_code == 201

    # Admin B creates Teacher B
    res_tb = await client.post(
        "/api/institution/teachers",
        headers=h_b,
        json={
            "email": "teacher_b@beta.edu",
            "password": "teacherPassB1",
            "full_name": "Teacher Beta",
        },
    )
    assert res_tb.status_code == 201

    # Admin A listing sees ONLY Teacher A, NEVER Teacher B
    list_a = await client.get("/api/institution/teachers", headers=h_a)
    assert list_a.status_code == 200
    items_a = list_a.json()
    assert len(items_a) == 1
    assert items_a[0]["email"] == "teacher_a@alpha.edu"
    assert items_a[0]["institution_id"] == inst_a["id"]

    # Admin B listing sees ONLY Teacher B, NEVER Teacher A
    list_b = await client.get("/api/institution/teachers", headers=h_b)
    assert list_b.status_code == 200
    items_b = list_b.json()
    assert len(items_b) == 1
    assert items_b[0]["email"] == "teacher_b@beta.edu"
    assert items_b[0]["institution_id"] == inst_b["id"]


@pytest.mark.asyncio
async def test_unauthorized_roles_cannot_manage_teachers(client: AsyncClient) -> None:
    """Students, independent teachers, platform admins, and unauthenticated users cannot manage institution teachers."""
    admin_token = await _create_user_and_token(
        client, "plat_admin@viva.edu", UserRole.ADMIN, "Plat Admin"
    )
    teacher_token = await _create_user_and_token(
        client, "reg_teacher@viva.edu", UserRole.TEACHER, "Reg Teacher"
    )
    student_token = await _create_user_and_token(
        client, "reg_student@viva.edu", UserRole.STUDENT, "Reg Student"
    )

    h_plat = {"Authorization": f"Bearer {admin_token}"}
    h_teach = {"Authorization": f"Bearer {teacher_token}"}
    h_stud = {"Authorization": f"Bearer {student_token}"}

    payload = {"email": "new_prof@viva.edu", "password": "password123", "full_name": "Prof"}

    # Unauthenticated -> 401
    assert (await client.post("/api/institution/teachers", json=payload)).status_code == 401
    assert (await client.get("/api/institution/teachers")).status_code == 401

    # Student -> 403
    assert (
        await client.post("/api/institution/teachers", headers=h_stud, json=payload)
    ).status_code == 403
    assert (await client.get("/api/institution/teachers", headers=h_stud)).status_code == 403

    # Teacher -> 403
    assert (
        await client.post("/api/institution/teachers", headers=h_teach, json=payload)
    ).status_code == 403
    assert (await client.get("/api/institution/teachers", headers=h_teach)).status_code == 403

    # Platform Admin (without institution) -> 403
    assert (
        await client.post("/api/institution/teachers", headers=h_plat, json=payload)
    ).status_code == 403
    assert (await client.get("/api/institution/teachers", headers=h_plat)).status_code == 403


@pytest.mark.asyncio
async def test_unassigned_institution_admin_rejected(client: AsyncClient) -> None:
    """An institution admin user without an assigned institution_id cannot manage teachers."""
    unassigned_token = await _create_user_and_token(
        client, "unassigned_admin@viva.edu", UserRole.INSTITUTION_ADMIN, "Unassigned Admin"
    )
    h_unassigned = {"Authorization": f"Bearer {unassigned_token}"}

    payload = {
        "email": "orphan_teacher@viva.edu",
        "password": "password123",
        "full_name": "Orphan Teacher",
    }
    assert (
        await client.post("/api/institution/teachers", headers=h_unassigned, json=payload)
    ).status_code == 403
    assert (await client.get("/api/institution/teachers", headers=h_unassigned)).status_code == 403


@pytest.mark.asyncio
async def test_duplicate_email_rejected_on_teacher_creation(client: AsyncClient) -> None:
    """Registering a teacher with an already registered email returns 409 Conflict."""
    admin_token = await _create_user_and_token(
        client, "dup_admin@viva.edu", UserRole.ADMIN, "Admin"
    )
    inst = (
        await client.post(
            "/api/admin/institutions",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"name": "Delta Tech", "code": "DT"},
        )
    ).json()
    await client.post(
        f"/api/admin/institutions/{inst['id']}/admins",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={
            "email": "dean_dt@delta.edu",
            "password": "deanPassword123",
            "full_name": "Dean Delta",
        },
    )
    token = (
        await client.post(
            "/api/auth/login", json={"email": "dean_dt@delta.edu", "password": "deanPassword123"}
        )
    ).json()["access_token"]
    h_admin = {"Authorization": f"Bearer {token}"}

    # First creation succeeds
    res1 = await client.post(
        "/api/institution/teachers",
        headers=h_admin,
        json={
            "email": "math_prof@delta.edu",
            "password": "mathPassword123",
            "full_name": "Math Prof",
        },
    )
    assert res1.status_code == 201

    # Second creation with identical email returns 409 Conflict
    res2 = await client.post(
        "/api/institution/teachers",
        headers=h_admin,
        json={
            "email": "math_prof@delta.edu",
            "password": "differentPassword123",
            "full_name": "Math Copy",
        },
    )
    assert res2.status_code == 409


@pytest.mark.asyncio
async def test_created_institution_teacher_can_login_and_create_courses(
    client: AsyncClient,
) -> None:
    """A teacher created by an institution admin can login and create courses."""
    admin_token = await _create_user_and_token(
        client, "course_test_admin@viva.edu", UserRole.ADMIN, "Admin"
    )
    inst = (
        await client.post(
            "/api/admin/institutions",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"name": "Gamma Institute", "code": "GI"},
        )
    ).json()
    await client.post(
        f"/api/admin/institutions/{inst['id']}/admins",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={
            "email": "dean_gi@gamma.edu",
            "password": "deanPassword123",
            "full_name": "Dean Gamma",
        },
    )
    token = (
        await client.post(
            "/api/auth/login", json={"email": "dean_gi@gamma.edu", "password": "deanPassword123"}
        )
    ).json()["access_token"]
    h_inst_admin = {"Authorization": f"Bearer {token}"}

    # Register teacher
    create_res = await client.post(
        "/api/institution/teachers",
        headers=h_inst_admin,
        json={
            "email": "prof_gamma@gamma.edu",
            "password": "gammaPassword123",
            "full_name": "Prof Gamma",
        },
    )
    assert create_res.status_code == 201

    # Teacher logs in
    login_res = await client.post(
        "/api/auth/login",
        json={"email": "prof_gamma@gamma.edu", "password": "gammaPassword123"},
    )
    assert login_res.status_code == 200
    teacher_token = login_res.json()["access_token"]
    h_teacher = {"Authorization": f"Bearer {teacher_token}"}

    # Teacher verifies profile
    me_res = await client.get("/api/auth/me", headers=h_teacher)
    assert me_res.status_code == 200
    me = me_res.json()
    assert me["role"] == "teacher"
    assert me["institution_id"] == inst["id"]

    # Teacher creates course
    course_res = await client.post(
        "/api/courses",
        headers=h_teacher,
        json={
            "name": "Quantum Computing",
            "code": "QC301",
            "description": "Qubits and entanglement",
        },
    )
    assert course_res.status_code == 201
    assert course_res.json()["code"] == "QC301"


@pytest.mark.asyncio
async def test_institution_admin_can_get_institution_profile(client: AsyncClient) -> None:
    """An authenticated institution admin can fetch their institution's public metadata."""
    admin_token = await _create_user_and_token(
        client, "prof_owner_admin@viva.edu", UserRole.ADMIN, "Admin"
    )
    inst = (
        await client.post(
            "/api/admin/institutions",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"name": "Metropolitan College of Science", "code": "MCS"},
        )
    ).json()

    await client.post(
        f"/api/admin/institutions/{inst['id']}/admins",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={
            "email": "dean_mcs@metropolitan.edu",
            "password": "deanPassword123",
            "full_name": "Dean Metro",
        },
    )
    token = (
        await client.post(
            "/api/auth/login",
            json={"email": "dean_mcs@metropolitan.edu", "password": "deanPassword123"},
        )
    ).json()["access_token"]
    h_inst_admin = {"Authorization": f"Bearer {token}"}

    # Fetch institution profile
    res = await client.get("/api/institution/profile", headers=h_inst_admin)
    assert res.status_code == 200
    data = res.json()
    assert data["id"] == inst["id"]
    assert data["name"] == "Metropolitan College of Science"
    assert data["code"] == "MCS"
    assert data["is_active"] is True
    assert "created_at" in data


@pytest.mark.asyncio
async def test_institution_profile_authorization_and_isolation(client: AsyncClient) -> None:
    """Only institution admins with an assigned institution can view their institution profile, with strict tenant isolation."""
    admin_token = await _create_user_and_token(
        client, "iso_plat_admin@viva.edu", UserRole.ADMIN, "Admin"
    )
    h_plat = {"Authorization": f"Bearer {admin_token}"}

    # Create Institution 1
    inst1 = (
        await client.post(
            "/api/admin/institutions", headers=h_plat, json={"name": "Northern Tech", "code": "NT1"}
        )
    ).json()
    await client.post(
        f"/api/admin/institutions/{inst1['id']}/admins",
        headers=h_plat,
        json={"email": "admin_nt@nt.edu", "password": "ntPassword123", "full_name": "Admin NT"},
    )
    token1 = (
        await client.post(
            "/api/auth/login", json={"email": "admin_nt@nt.edu", "password": "ntPassword123"}
        )
    ).json()["access_token"]

    # Create Institution 2
    inst2 = (
        await client.post(
            "/api/admin/institutions",
            headers=h_plat,
            json={"name": "Southern Academy", "code": "SA2"},
        )
    ).json()
    await client.post(
        f"/api/admin/institutions/{inst2['id']}/admins",
        headers=h_plat,
        json={"email": "admin_sa@sa.edu", "password": "saPassword123", "full_name": "Admin SA"},
    )
    token2 = (
        await client.post(
            "/api/auth/login", json={"email": "admin_sa@sa.edu", "password": "saPassword123"}
        )
    ).json()["access_token"]

    # 1. Admin NT gets only Institution NT1
    res1 = await client.get(
        "/api/institution/profile", headers={"Authorization": f"Bearer {token1}"}
    )
    assert res1.status_code == 200
    assert res1.json()["id"] == inst1["id"]
    assert res1.json()["code"] == "NT1"

    # 2. Admin SA gets only Institution SA2
    res2 = await client.get(
        "/api/institution/profile", headers={"Authorization": f"Bearer {token2}"}
    )
    assert res2.status_code == 200
    assert res2.json()["id"] == inst2["id"]
    assert res2.json()["code"] == "SA2"

    # 3. Unauthenticated request -> 401
    assert (await client.get("/api/institution/profile")).status_code == 401

    # 4. Student -> 403
    student_token = await _create_user_and_token(
        client, "iso_stud@viva.edu", UserRole.STUDENT, "Student"
    )
    assert (
        await client.get(
            "/api/institution/profile", headers={"Authorization": f"Bearer {student_token}"}
        )
    ).status_code == 403

    # 5. Teacher -> 403
    teacher_token = await _create_user_and_token(
        client, "iso_teach@viva.edu", UserRole.TEACHER, "Teacher"
    )
    assert (
        await client.get(
            "/api/institution/profile", headers={"Authorization": f"Bearer {teacher_token}"}
        )
    ).status_code == 403

    # 6. Platform Admin (without institution) -> 403
    assert (await client.get("/api/institution/profile", headers=h_plat)).status_code == 403
