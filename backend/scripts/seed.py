"""Comprehensive database seed script for Parakh AI demo and testing.

Seeds:
1. Institution (Apex Institute of Technology)
2. Platform Admin, Institution Admin, Teacher, and Student accounts
3. Courses (Data Structures & Algorithms, Operating Systems) with syllabi and topics
4. Curriculum reference document with FAISS embeddings
5. Approved Question Bank entries across topics and difficulty tiers
6. Custom Oral Assessment (published)
7. Scheduled Assignment with deadlines
8. Completed student viva sessions with realistic transcripts, rubrics, and scores
9. Student privacy consent records
"""

from __future__ import annotations

import asyncio
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

# Add backend directory to sys.path
backend_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_dir))

from sqlalchemy import select

from app.database import AsyncSessionLocal, Base, engine
from app.models.answer import Answer
from app.models.assessment import Assessment
from app.models.assignment import Assignment
from app.models.consent import Consent
from app.models.course import Course
from app.models.document import Document, DocumentStatus
from app.models.institution import Institution
from app.models.question import Question, QuestionDifficulty
from app.models.topic import Topic
from app.models.user import User, UserRole
from app.models.viva_session import VivaSession, VivaStatus
from app.services.auth_service import hash_password
from app.services.rag_service import build_index, chunk_text


async def seed() -> None:
    print("=" * 70)
    print(" Parakh AI — One-Command Demo Seed Script")
    print("=" * 70)

    # Ensure all tables exist
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with AsyncSessionLocal() as db:
        # 1. Institution
        print("\n[1/8] Seeding Institution...")
        inst_res = await db.execute(select(Institution).where(Institution.code == "APEX"))
        institution = inst_res.scalar_one_or_none()
        if not institution:
            institution = Institution(
                name="Apex Institute of Technology",
                code="APEX",
                is_active=True,
            )
            db.add(institution)
            await db.flush()
            print(f"  [+] Created Institution: {institution.name} ({institution.code})")
        else:
            print(f"  [.] Institution exists: {institution.name}")

        # 2. Users (Admin, Institution Admin, Teacher, Students)
        print("\n[2/8] Seeding Users across all roles...")
        users_data = [
            ("admin@apex.edu", "admin123", "System Administrator", UserRole.ADMIN, None),
            (
                "instadmin@apex.edu",
                "instadmin123",
                "Dr. Ramesh Gupta",
                UserRole.INSTITUTION_ADMIN,
                institution.id,
            ),
            (
                "teacher@apex.edu",
                "teacher123",
                "Dr. Alan Turing",
                UserRole.TEACHER,
                institution.id,
            ),
            (
                "student@apex.edu",
                "student123",
                "Ada Lovelace",
                UserRole.STUDENT,
                institution.id,
            ),
            (
                "ananya@apex.edu",
                "student123",
                "Ananya Sen",
                UserRole.STUDENT,
                institution.id,
            ),
            (
                "rohit@apex.edu",
                "student123",
                "Rohit Verma",
                UserRole.STUDENT,
                institution.id,
            ),
        ]

        users: dict[str, User] = {}
        for email, password, full_name, role, inst_id in users_data:
            res = await db.execute(select(User).where(User.email == email))
            user = res.scalar_one_or_none()
            if not user:
                user = User(
                    email=email,
                    hashed_password=hash_password(password),
                    full_name=full_name,
                    role=role,
                    institution_id=inst_id,
                )
                db.add(user)
                await db.flush()
                print(f"  [+] Created {role.value.upper()}: {full_name} <{email}>")
            else:
                print(f"  [.] User exists: {full_name} <{email}>")
            users[email] = user
        await db.commit()

        teacher = users["teacher@apex.edu"]
        student_ada = users["student@apex.edu"]
        student_ananya = users["ananya@apex.edu"]
        student_rohit = users["rohit@apex.edu"]

        # 3. Courses
        print("\n[3/8] Seeding Courses & Syllabi...")
        c_res = await db.execute(select(Course).where(Course.code == "CS201"))
        course_cs201 = c_res.scalar_one_or_none()
        if not course_cs201:
            course_cs201 = Course(
                teacher_id=teacher.id,
                name="Data Structures & Algorithms",
                code="CS201",
                subject="Computer Science",
                academic_level="Undergraduate",
                description="Core undergraduate course covering abstract data types, trees, graph algorithms, and asymptotic complexity.",
                syllabus_text=(
                    "Module 1: Linear Data Structures - Arrays, Stacks, Queues, Linked Lists.\n"
                    "Module 2: Non-Linear Structures - Binary Trees, Binary Search Trees, AVL Trees, Heaps.\n"
                    "Module 3: Graph Algorithms - Breadth-First Search, Depth-First Search, Shortest Paths, Topological Sort.\n"
                    "Module 4: Algorithm Strategies - Divide and Conquer, Dynamic Programming, Greedy Algorithms, Asymptotic Notation."
                ),
                interview_config={
                    "max_questions": 5,
                    "max_duration_sec": 900,
                    "difficulty": "medium",
                    "topic_ids": [],
                },
            )
            db.add(course_cs201)
            await db.flush()
            print(f"  [+] Created Course: {course_cs201.name} ({course_cs201.code})")
        else:
            course_cs201.teacher_id = teacher.id
            course_cs201.name = "Data Structures & Algorithms"
            print(f"  [.] Course exists: {course_cs201.code}")

        c_res2 = await db.execute(select(Course).where(Course.code == "CS301"))
        course_cs301 = c_res2.scalar_one_or_none()
        if not course_cs301:
            course_cs301 = Course(
                teacher_id=teacher.id,
                name="Operating Systems",
                code="CS301",
                subject="Computer Science",
                academic_level="Undergraduate",
                description="Fundamental concepts of OS: processes, threads, concurrency, memory management, and file systems.",
                syllabus_text="Processes, Threads, Scheduling, Semaphores, Deadlocks, Virtual Memory.",
                interview_config={
                    "max_questions": 4,
                    "max_duration_sec": 600,
                    "difficulty": "medium",
                    "topic_ids": [],
                },
            )
            db.add(course_cs301)
            await db.flush()
            print(f"  [+] Created Course: {course_cs301.name} ({course_cs301.code})")

        # 4. Topics
        print("\n[4/8] Seeding Course Topics...")
        topics_info = [
            ("Arrays, Stacks & Queues", 1),
            ("Trees & Binary Search Trees", 2),
            ("Graph Traversal Algorithms", 3),
            ("Sorting & Dynamic Programming", 4),
        ]
        topics: dict[str, Topic] = {}
        for name, order in topics_info:
            t_res = await db.execute(
                select(Topic).where(Topic.course_id == course_cs201.id, Topic.name == name)
            )
            topic = t_res.scalar_one_or_none()
            if not topic:
                topic = Topic(course_id=course_cs201.id, name=name, sort_order=order)
                db.add(topic)
                await db.flush()
                print(f"  [+] Added Topic: {name}")
            else:
                print(f"  [.] Topic exists: {name}")
            topics[name] = topic
        await db.commit()

        # 5. Curriculum Reference Document & RAG FAISS Index
        print("\n[5/8] Ingesting Curriculum Document & Building Embedding Index...")
        bst_topic = topics["Trees & Binary Search Trees"]
        doc_res = await db.execute(
            select(Document).where(
                Document.topic_id == bst_topic.id, Document.filename == "bst_lecture_notes.txt"
            )
        )
        doc = doc_res.scalar_one_or_none()
        doc_text = (
            "A Binary Search Tree (BST) is a node-based binary tree data structure with the property that the key in each node "
            "must be greater than or equal to any key stored in the left sub-tree, and less than or equal to any key in the right sub-tree.\n\n"
            "Search and insertion in a balanced BST take O(log n) time. However, in the worst-case scenario where elements are inserted in sorted order, "
            "the tree degenerates into a linear linked list with height n, causing operations to take O(n) time.\n\n"
            "Self-balancing binary search trees such as AVL Trees and Red-Black Trees maintain a balanced height of O(log n) "
            "through tree rotations after insertion and deletion, guaranteeing logarithmic worst-case search time."
        )

        uploads_dir = backend_dir / "uploads"
        uploads_dir.mkdir(parents=True, exist_ok=True)
        file_path = uploads_dir / "seed_bst_lecture_notes.txt"
        file_path.write_text(doc_text, encoding="utf-8")

        chunks = chunk_text(doc_text, chunk_size=200, overlap=30)
        build_index(bst_topic.id, chunks)

        if not doc:
            doc = Document(
                topic_id=bst_topic.id,
                filename="bst_lecture_notes.txt",
                file_path=str(file_path),
                content_hash="seed_bst_hash_v1",
                status=DocumentStatus.EMBEDDED,
                chunk_count=len(chunks),
            )
            db.add(doc)
            await db.commit()
            print(f"  [+] Ingested and indexed '{doc.filename}' ({len(chunks)} chunks)")
        else:
            print(f"  [.] Document exists: {doc.filename}")

        # 6. Question Bank
        print("\n[6/8] Seeding Approved Question Bank...")
        questions_data = [
            (
                "Arrays, Stacks & Queues",
                "How does a stack differ from a queue, and what operations does each support?",
                ["stack uses last-in first-out", "queue uses first-in first-out", "push and pop", "enqueue and dequeue"],
                QuestionDifficulty.EASY,
            ),
            (
                "Arrays, Stacks & Queues",
                "When would you choose a linked list over an array, and what trade-offs does that introduce?",
                ["dynamic size", "insertion and deletion without shifting", "no constant-time indexed access", "extra pointer memory"],
                QuestionDifficulty.MEDIUM,
            ),
            (
                "Trees & Binary Search Trees",
                "What property makes a binary search tree useful, and what is its worst-case search complexity?",
                ["left values are smaller", "right values are larger", "average logarithmic search", "worst case linear when unbalanced"],
                QuestionDifficulty.MEDIUM,
            ),
            (
                "Trees & Binary Search Trees",
                "How can balancing a binary search tree improve its performance?",
                ["limits tree height", "keeps operations logarithmic", "rotations preserve search order"],
                QuestionDifficulty.HARD,
            ),
            (
                "Trees & Binary Search Trees",
                "Explain the in-order traversal of a binary search tree and its notable output property.",
                ["visits left, root, right", "produces keys in ascending sorted order", "runs in O(n) time"],
                QuestionDifficulty.EASY,
            ),
            (
                "Graph Traversal Algorithms",
                "Compare breadth-first search and depth-first search, including one use case for each.",
                ["BFS explores level by level", "DFS explores a path deeply", "BFS finds shortest paths in unweighted graphs", "DFS supports cycle detection"],
                QuestionDifficulty.MEDIUM,
            ),
            (
                "Graph Traversal Algorithms",
                "What data structures do breadth-first search and depth-first search typically use?",
                ["BFS uses a queue", "DFS uses a stack or recursion", "visited set prevents repeated exploration"],
                QuestionDifficulty.EASY,
            ),
            (
                "Sorting & Dynamic Programming",
                "How does merge sort work, and what are its time and auxiliary-space complexities?",
                ["divide and conquer", "splits and merges sorted halves", "O(n log n) time", "O(n) auxiliary space"],
                QuestionDifficulty.MEDIUM,
            ),
            (
                "Sorting & Dynamic Programming",
                "How does dynamic programming avoid repeated work, and when is it applicable?",
                ["overlapping subproblems", "optimal substructure", "memoization or tabulation", "stores and reuses results"],
                QuestionDifficulty.HARD,
            ),
        ]

        seeded_questions: list[Question] = []
        for topic_name, text, key_points, difficulty in questions_data:
            q_res = await db.execute(
                select(Question).where(
                    Question.topic_id == topics[topic_name].id,
                    Question.question_text == text,
                )
            )
            question = q_res.scalar_one_or_none()
            if not question:
                question = Question(
                    topic_id=topics[topic_name].id,
                    question_text=text,
                    expected_key_points=key_points,
                    difficulty=difficulty,
                    is_approved=True,
                    generated_by=teacher.id,
                    prompt_version="seed_v2",
                )
                db.add(question)
                await db.flush()
                print(f"  [+] Added Question ({difficulty.value}): {text[:45]}...")
            seeded_questions.append(question)
        await db.commit()

        # CS301 topics and questions so its practice viva can start
        os_data = {
            "Processes & Threads": [
                ("What is the difference between a process and a thread?",
                 ["process has its own address space", "threads share memory within a process", "context switch cost differs"],
                 QuestionDifficulty.EASY),
                ("What happens during a context switch and why is it costly?",
                 ["save and restore CPU state", "scheduler picks next task", "cache and TLB effects"],
                 QuestionDifficulty.MEDIUM),
            ],
            "Deadlocks & Synchronization": [
                ("What are the four necessary conditions for deadlock?",
                 ["mutual exclusion", "hold and wait", "no preemption", "circular wait"],
                 QuestionDifficulty.MEDIUM),
                ("How does a semaphore differ from a mutex?",
                 ["semaphore is a counter", "mutex has an owner", "binary semaphore is not a mutex"],
                 QuestionDifficulty.MEDIUM),
            ],
            "Virtual Memory": [
                ("What is paging and how does a page fault get handled?",
                 ["fixed-size pages and frames", "page table translation", "OS loads page from disk on fault"],
                 QuestionDifficulty.HARD),
            ],
        }
        for order, (tname, qs) in enumerate(os_data.items(), start=1):
            t_res = await db.execute(
                select(Topic).where(Topic.course_id == course_cs301.id, Topic.name == tname)
            )
            os_topic = t_res.scalar_one_or_none()
            if not os_topic:
                os_topic = Topic(course_id=course_cs301.id, name=tname, sort_order=order)
                db.add(os_topic)
                await db.flush()
            for text, key_points, difficulty in qs:
                q_res = await db.execute(
                    select(Question).where(
                        Question.topic_id == os_topic.id, Question.question_text == text
                    )
                )
                if not q_res.scalar_one_or_none():
                    db.add(
                        Question(
                            topic_id=os_topic.id,
                            question_text=text,
                            expected_key_points=key_points,
                            difficulty=difficulty,
                            is_approved=True,
                            generated_by=teacher.id,
                            prompt_version="seed_v2",
                        )
                    )
        await db.commit()

        # 7. Custom Assessment & Scheduled Assignment
        print("\n[7/8] Seeding Custom Assessment & Assignment...")
        asst_res = await db.execute(
            select(Assessment).where(
                Assessment.course_id == course_cs201.id,
                Assessment.title == "CS201 Midterm Oral Assessment",
            )
        )
        assessment = asst_res.scalar_one_or_none()
        selected_qids = [str(q.id) for q in seeded_questions[:4]]
        if not assessment:
            assessment = Assessment(
                teacher_id=teacher.id,
                course_id=course_cs201.id,
                title="CS201 Midterm Oral Assessment",
                description="Midterm oral evaluation testing foundational data structures, BSTs, and traversals.",
                instructions="Answer clearly and explain the trade-offs in your own words. Each question allows up to 2 minutes.",
                duration_minutes=15,
                max_questions=4,
                difficulty="medium",
                is_published=True,
                question_ids=selected_qids,
                topic_ids=[str(t.id) for t in topics.values()],
            )
            db.add(assessment)
            await db.flush()
            print(f"  [+] Created Published Assessment: {assessment.title}")
        else:
            print(f"  [.] Assessment exists: {assessment.title}")

        assign_res = await db.execute(
            select(Assignment).where(
                Assignment.course_id == course_cs201.id,
                Assignment.title == "Midterm Oral Viva (Fall 2026)",
            )
        )
        assignment = assign_res.scalar_one_or_none()
        now = datetime.now(UTC)
        if not assignment:
            assignment = Assignment(
                teacher_id=teacher.id,
                course_id=course_cs201.id,
                assessment_id=assessment.id,
                title="Midterm Oral Viva (Fall 2026)",
                instructions="Complete this mandatory assessment before the deadline. Two attempts allowed.",
                start_date=now - timedelta(days=2),
                deadline=now + timedelta(days=7),
                attempt_limit=2,
                is_active=True,
                assigned_student_ids=[str(student_ada.id), str(student_ananya.id), str(student_rohit.id)],
            )
            db.add(assignment)
            await db.flush()
            print(f"  [+] Created Active Assignment: {assignment.title} (Deadline: +7 days)")
        else:
            print(f"  [.] Assignment exists: {assignment.title}")
        await db.commit()

        # 8. Student Consents & Completed Viva Sessions
        print("\n[8/8] Seeding Student Consents & Scored Viva Sessions...")
        for student in [student_ada, student_ananya, student_rohit]:
            c_res = await db.execute(select(Consent).where(Consent.user_id == student.id))
            if not c_res.scalars().first():
                db.add(
                    Consent(
                        user_id=student.id,
                        audio_retention_consent=True,
                        transcript_consent=True,
                    )
                )
        await db.commit()

        # Check existing sessions
        sess_res = await db.execute(
            select(VivaSession).where(
                VivaSession.course_id == course_cs201.id,
                VivaSession.student_id.in_(
                    [student_ada.id, student_ananya.id, student_rohit.id]
                ),
            )
        )
        existing_sessions = sess_res.scalars().all()
        if not existing_sessions:
            # Session 1: Ada Lovelace - High Mastery (Score 0.85)
            s1 = VivaSession(
                student_id=student_ada.id,
                course_id=course_cs201.id,
                status=VivaStatus.COMPLETED,
                max_questions=3,
                max_duration_sec=900,
                current_question_index=3,
                total_score=0.85,
                config={"is_adaptive": True},
                started_at=now - timedelta(days=1, hours=2),
                finished_at=now - timedelta(days=1, hours=1, minutes=45),
            )
            db.add(s1)
            await db.flush()

            # Answers for s1
            a1 = Answer(
                session_id=s1.id,
                question_id=seeded_questions[0].id,  # Stacks vs Queues
                sequence_number=1,
                transcript="A stack operates on a last-in first-out principle using push and pop operations, whereas a queue is first-in first-out with enqueue and dequeue.",
                embedding_score=0.88,
                llm_score=0.86,
                fused_score=0.87,
                rubric_breakdown={"correctness": 9.0, "completeness": 8.5, "clarity": 8.6},
                latency_ms=1250.0,
            )
            a2 = Answer(
                session_id=s1.id,
                question_id=seeded_questions[2].id,  # BST properties
                sequence_number=2,
                transcript="In a binary search tree, all left subtree values are strictly smaller and right values are larger. Search is logarithmic on average, but degrades to linear O(n) if unbalanced.",
                embedding_score=0.86,
                llm_score=0.84,
                fused_score=0.85,
                rubric_breakdown={"correctness": 8.8, "completeness": 8.4, "clarity": 8.3},
                latency_ms=1400.0,
            )
            a3 = Answer(
                session_id=s1.id,
                question_id=seeded_questions[5].id,  # BFS vs DFS
                sequence_number=3,
                transcript="BFS explores neighbors level-by-level using a FIFO queue, ideal for shortest paths in unweighted graphs. DFS explores branches deeply using recursion or a stack.",
                embedding_score=0.84,
                llm_score=0.82,
                fused_score=0.83,
                rubric_breakdown={"correctness": 8.5, "completeness": 8.2, "clarity": 8.2},
                latency_ms=1320.0,
            )
            db.add_all([a1, a2, a3])

            # Session 2: Ananya Sen - Developing in Graph Traversals (Score 0.62) -> Demonstrates Weakness Detection (P2.9)
            s2 = VivaSession(
                student_id=student_ananya.id,
                course_id=course_cs201.id,
                status=VivaStatus.COMPLETED,
                max_questions=3,
                max_duration_sec=900,
                current_question_index=3,
                total_score=0.62,
                config={"is_adaptive": True},
                started_at=now - timedelta(hours=5),
                finished_at=now - timedelta(hours=4, minutes=45),
            )
            db.add(s2)
            await db.flush()

            a2_1 = Answer(
                session_id=s2.id,
                question_id=seeded_questions[2].id,  # BST
                sequence_number=1,
                transcript="A binary search tree has smaller values on the left and larger on the right. Average search is O(log n).",
                embedding_score=0.82,
                llm_score=0.80,
                fused_score=0.81,
                rubric_breakdown={"correctness": 8.5, "completeness": 7.8, "clarity": 8.0},
                latency_ms=1100.0,
            )
            a2_2 = Answer(
                session_id=s2.id,
                question_id=seeded_questions[5].id,  # BFS vs DFS
                sequence_number=2,
                transcript="BFS and DFS are search algorithms. I think BFS uses a stack and DFS uses a queue to traverse nodes.",
                embedding_score=0.44,
                llm_score=0.40,
                fused_score=0.42,
                rubric_breakdown={"correctness": 4.0, "completeness": 4.0, "clarity": 4.5},
                latency_ms=1550.0,
            )
            a2_3 = Answer(
                session_id=s2.id,
                question_id=seeded_questions[6].id,  # Graph traversal data structures
                sequence_number=3,
                transcript="I know visited lists are used, but I get confused between queues and recursion for graphs.",
                embedding_score=0.62,
                llm_score=0.64,
                fused_score=0.63,
                rubric_breakdown={"correctness": 6.5, "completeness": 6.0, "clarity": 6.4},
                latency_ms=1200.0,
            )
            db.add_all([a2_1, a2_2, a2_3])

            # Session 3: Ada Lovelace - Assignment Submission (Score 0.89)
            s3 = VivaSession(
                student_id=student_ada.id,
                course_id=course_cs201.id,
                status=VivaStatus.COMPLETED,
                max_questions=2,
                max_duration_sec=900,
                current_question_index=2,
                total_score=0.89,
                config={
                    "assignment_id": str(assignment.id),
                    "assessment_id": str(assessment.id),
                    "is_adaptive": False,
                },
                started_at=now - timedelta(hours=3),
                finished_at=now - timedelta(hours=2, minutes=45),
            )
            db.add(s3)
            await db.flush()

            a3_1 = Answer(
                session_id=s3.id,
                question_id=seeded_questions[0].id,
                sequence_number=1,
                transcript="Stacks follow LIFO while queues follow FIFO. Stacks push and pop from the top; queues enqueue at the rear and dequeue from the front.",
                embedding_score=0.91,
                llm_score=0.88,
                fused_score=0.89,
                rubric_breakdown={"correctness": 9.2, "completeness": 8.8, "clarity": 8.7},
                latency_ms=1300.0,
            )
            a3_2 = Answer(
                session_id=s3.id,
                question_id=seeded_questions[3].id,
                sequence_number=2,
                transcript="Balancing maintains the logarithmic tree height O(log n), preventing worst-case linear performance during searches and insertions through rotation operations.",
                embedding_score=0.89,
                llm_score=0.87,
                fused_score=0.88,
                rubric_breakdown={"correctness": 9.0, "completeness": 8.6, "clarity": 8.8},
                latency_ms=1450.0,
            )
            db.add_all([a3_1, a3_2])
            await db.commit()
            print("  [+] Created 3 realistic completed viva sessions with scored answers and rubrics")
        else:
            print("  [.] Completed viva sessions already present")

    print("\n" + "=" * 70)
    print(" [OK] Parakh AI Database Seeded Successfully!")
    print("=" * 70)
    print("\nDemo Accounts Created:")
    print("  * Platform Admin:    admin@apex.edu       / admin123     (Workspace: #/admin)")
    print("  * Institution Admin: instadmin@apex.edu   / instadmin123 (Workspace: #/institution)")
    print("  * Teacher:           teacher@apex.edu     / teacher123   (Workspace: #/teacher)")
    print("  * Student (Ada):     student@apex.edu     / student123   (Workspace: #/)")
    print("  * Student (Ananya):  ananya@apex.edu      / student123   (Workspace: #/)")
    print("  * Student (Rohit):   rohit@apex.edu       / student123   (Workspace: #/)")
    print("\nSample Data Ready:")
    print("  - Institution:       Apex Institute of Technology (APEX)")
    print("  - Courses:           CS201 (Data Structures), CS301 (Operating Systems)")
    print("  - RAG Documents:     bst_lecture_notes.txt (FAISS index active)")
    print("  - Question Bank:     9 approved questions across 4 topics")
    print("  - Assessment:        CS201 Midterm Oral Assessment (Published)")
    print("  - Assignment:        Midterm Oral Viva (Fall 2026) (Active, 7 days remaining)")
    print("  - Student Vivas:     3 completed sessions with transcripts, rubrics, and scores")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(seed())
