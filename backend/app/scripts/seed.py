"""Database seed script for development and testing."""

import asyncio
import sys
from pathlib import Path

# Add backend directory to sys.path so app can be imported
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models.consent import Consent
from app.models.course import Course
from app.models.question import Question, QuestionDifficulty
from app.models.topic import Topic
from app.models.user import User, UserRole
from app.services.auth_service import hash_password


async def seed_database() -> None:
    """Populate database with sample teacher, student, course, topics, and consent."""
    print("[*] Seeding database...")
    async with AsyncSessionLocal() as session:
        # 1. Create Teacher
        teacher_email = "teacher@viva.edu"
        result = await session.execute(select(User).where(User.email == teacher_email))
        teacher = result.scalar_one_or_none()
        if not teacher:
            teacher = User(
                email=teacher_email,
                hashed_password=hash_password("teacher123"),
                full_name="Dr. Alan Turing",
                role=UserRole.TEACHER,
            )
            session.add(teacher)
            await session.commit()
            await session.refresh(teacher)
            print(f"[+] Created Teacher: {teacher.email} (id={teacher.id})")
        else:
            print(f"[-] Teacher already exists: {teacher.email}")

        # 2. Create Student
        student_email = "student@viva.edu"
        result = await session.execute(select(User).where(User.email == student_email))
        student = result.scalar_one_or_none()
        if not student:
            student = User(
                email=student_email,
                hashed_password=hash_password("student123"),
                full_name="Ada Lovelace",
                role=UserRole.STUDENT,
            )
            session.add(student)
            await session.commit()
            await session.refresh(student)
            print(f"[+] Created Student: {student.email} (id={student.id})")
        else:
            print(f"[-] Student already exists: {student.email}")

        # 3. Create Course
        course_code = "CS201"
        result = await session.execute(select(Course).where(Course.code == course_code))
        course = result.scalar_one_or_none()
        if not course:
            course = Course(
                teacher_id=teacher.id,
                name="Data Structures & Algorithms",
                code=course_code,
                description="Core computer science course covering linear and non-linear data structures, searching, and sorting.",
            )
            session.add(course)
            await session.commit()
            await session.refresh(course)
            print(f"[+] Created Course: {course.name} ({course.code})")
        else:
            print(f"[-] Course already exists: {course.code}")

        # 4. Create Topics
        topics_data = [
            ("Arrays, Stacks & Queues", 1),
            ("Trees & Binary Search Trees", 2),
            ("Graph Traversal Algorithms", 3),
            ("Sorting & Dynamic Programming", 4),
        ]
        topic_ids = {}
        for name, order in topics_data:
            t_res = await session.execute(
                select(Topic).where(Topic.course_id == course.id, Topic.name == name)
            )
            topic = t_res.scalar_one_or_none()
            if topic is None:
                topic = Topic(
                    course_id=course.id,
                    name=name,
                    sort_order=order,
                )
                session.add(topic)
                await session.flush()
                print(f"  [+] Added Topic: {name}")
            topic_ids[name] = topic.id
        await session.commit()

        # 5. Add approved questions so the seeded course can be used for a viva.
        questions_data = [
            (
                "Arrays, Stacks & Queues",
                "How does a stack differ from a queue, and what operations does each support?",
                [
                    "stack uses last-in first-out",
                    "queue uses first-in first-out",
                    "push and pop",
                    "enqueue and dequeue",
                ],
                QuestionDifficulty.EASY,
            ),
            (
                "Arrays, Stacks & Queues",
                "When would you choose a linked list over an array, and what trade-offs does that introduce?",
                [
                    "dynamic size",
                    "insertion and deletion without shifting",
                    "no constant-time indexed access",
                    "extra pointer memory",
                ],
                QuestionDifficulty.MEDIUM,
            ),
            (
                "Trees & Binary Search Trees",
                "What property makes a binary search tree useful, and what is its worst-case search complexity?",
                [
                    "left values are smaller",
                    "right values are larger",
                    "average logarithmic search",
                    "worst case linear when unbalanced",
                ],
                QuestionDifficulty.MEDIUM,
            ),
            (
                "Trees & Binary Search Trees",
                "How can balancing a binary search tree improve its performance?",
                [
                    "limits tree height",
                    "keeps operations logarithmic",
                    "rotations preserve search order",
                ],
                QuestionDifficulty.HARD,
            ),
            (
                "Graph Traversal Algorithms",
                "Compare breadth-first search and depth-first search, including one use case for each.",
                [
                    "BFS explores level by level",
                    "DFS explores a path deeply",
                    "BFS finds shortest paths in unweighted graphs",
                    "DFS supports cycle detection",
                ],
                QuestionDifficulty.MEDIUM,
            ),
            (
                "Graph Traversal Algorithms",
                "What data structures do breadth-first search and depth-first search typically use?",
                [
                    "BFS uses a queue",
                    "DFS uses a stack or recursion",
                    "visited set prevents repeated exploration",
                ],
                QuestionDifficulty.EASY,
            ),
            (
                "Sorting & Dynamic Programming",
                "How does merge sort work, and what are its time and auxiliary-space complexities?",
                [
                    "divide and conquer",
                    "splits and merges sorted halves",
                    "O(n log n) time",
                    "O(n) auxiliary space",
                ],
                QuestionDifficulty.MEDIUM,
            ),
            (
                "Sorting & Dynamic Programming",
                "How does dynamic programming avoid repeated work, and when is it applicable?",
                [
                    "overlapping subproblems",
                    "optimal substructure",
                    "memoization or tabulation",
                    "stores and reuses results",
                ],
                QuestionDifficulty.HARD,
            ),
        ]
        for topic_name, text, key_points, difficulty in questions_data:
            q_res = await session.execute(
                select(Question).where(
                    Question.topic_id == topic_ids[topic_name],
                    Question.question_text == text,
                )
            )
            if q_res.scalar_one_or_none() is None:
                session.add(
                    Question(
                        topic_id=topic_ids[topic_name],
                        question_text=text,
                        expected_key_points=key_points,
                        difficulty=difficulty,
                        is_approved=True,
                        generated_by=teacher.id,
                        prompt_version="seed_v1",
                    )
                )
        await session.commit()

        # 6. Create Initial Student Consent
        c_res = await session.execute(select(Consent).where(Consent.user_id == student.id))
        if c_res.scalars().first() is None:
            consent = Consent(
                user_id=student.id,
                audio_retention_consent=True,
                transcript_consent=True,
            )
            session.add(consent)
            await session.commit()
            print("[+] Added baseline student consent record")

        print("[OK] Seeding completed successfully!")


if __name__ == "__main__":
    asyncio.run(seed_database())
