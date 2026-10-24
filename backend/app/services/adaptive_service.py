"""Adaptive viva examination service for personalized questioning, difficulty progression, and learning summaries."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.answer import Answer
from app.models.question import Question, QuestionDifficulty
from app.models.topic import Topic
from app.models.viva_session import VivaSession


class AdaptiveVivaService:
    """Core intelligence engine for adaptive questioning, difficulty tuning, and session summaries."""

    @staticmethod
    def is_adaptive_session(session: VivaSession) -> bool:
        """Determine if a session should use adaptive question selection."""
        config = session.config or {}
        # Fixed assessments and assignments MUST remain static and un-adaptive
        if config.get("assignment_id") or config.get("assessment_id"):
            return False
        if config.get("question_ids"):
            return False
        if config.get("is_adaptive") is False:
            return False
        if config.get("is_adaptive") is True:
            return True
        # If is_adaptive is not explicitly defined in config, legacy sessions with question_order remain static
        if config.get("question_order"):
            return False
        return True

    @staticmethod
    def compute_next_difficulty(
        current_difficulty: str | QuestionDifficulty,
        session_scores: list[float],
        historical_topic_avg: float | None = None,
    ) -> QuestionDifficulty:
        """Adapt question difficulty based on demonstrated performance using gradual, transparent rules."""
        if isinstance(current_difficulty, QuestionDifficulty):
            current_level = current_difficulty.value
        else:
            current_level = str(current_difficulty or "medium").lower()

        if current_level not in ("easy", "medium", "hard"):
            current_level = "medium"

        # Baseline with no session answers yet
        if not session_scores:
            if historical_topic_avg is not None and historical_topic_avg < 0.50:
                return QuestionDifficulty.EASY
            return QuestionDifficulty(current_level)

        # Single answer: avoid dramatic swings after a single unusual answer
        if len(session_scores) == 1:
            return QuestionDifficulty(current_level)

        # Window of recent 2 answers
        recent = session_scores[-2:]
        recent_avg = sum(recent) / len(recent)

        # Consistent strong performance: step up
        if all(s >= 0.75 for s in recent) or recent_avg >= 0.80:
            if current_level == "easy":
                return QuestionDifficulty.MEDIUM
            if current_level == "medium":
                return QuestionDifficulty.HARD
            return QuestionDifficulty.HARD

        # Inconsistent or struggling performance: step down to reinforce foundational concepts
        if all(s < 0.50 for s in recent) or recent_avg < 0.50:
            if current_level == "hard":
                return QuestionDifficulty.MEDIUM
            if current_level == "medium":
                return QuestionDifficulty.EASY
            return QuestionDifficulty.EASY

        # In-between / mixed performance: sustain current difficulty
        return QuestionDifficulty(current_level)

    @staticmethod
    async def get_student_topic_performance(
        db: AsyncSession,
        student_id: uuid.UUID,
        course_id: uuid.UUID,
    ) -> dict[uuid.UUID, dict[str, Any]]:
        """Retrieve historical topic-level evaluation metrics for the student in this course."""
        result = await db.execute(
            select(Answer, Question.topic_id)
            .join(Question, Answer.question_id == Question.id)
            .join(Topic, Question.topic_id == Topic.id)
            .join(VivaSession, Answer.session_id == VivaSession.id)
            .where(
                VivaSession.student_id == student_id,
                Topic.course_id == course_id,
            )
        )
        records = result.all()
        topic_map: dict[uuid.UUID, dict[str, Any]] = {}

        for answer, topic_id in records:
            score = (
                answer.fused_score
                if answer.fused_score is not None
                else (answer.llm_score if answer.llm_score is not None else answer.embedding_score)
            )
            if score is None:
                continue

            if topic_id not in topic_map:
                topic_map[topic_id] = {
                    "scores": [],
                    "count": 0,
                    "avg_score": None,
                    "status": "untested",
                }
            topic_map[topic_id]["scores"].append(float(score))
            topic_map[topic_id]["count"] += 1

        for _t_id, data in topic_map.items():
            sc = data["scores"]
            avg = sum(sc) / len(sc)
            data["avg_score"] = round(avg, 4)
            if avg < 0.60:
                data["status"] = "weak"
            elif avg < 0.75:
                data["status"] = "developing"
            else:
                data["status"] = "strong"

        return topic_map

    @classmethod
    async def select_next_topic(
        cls,
        db: AsyncSession,
        session: VivaSession,
        course_topics: list[Topic],
        session_answers: list[Answer],
    ) -> Topic | None:
        """Select the next topic to practice, prioritizing weak topics while avoiding topic fixation."""
        if not course_topics:
            return None

        config = session.config or {}
        configured_topic_ids = [uuid.UUID(str(tid)) for tid in config.get("topic_ids", []) if tid]

        # Targeted single-topic practice preserves focus on the chosen topic
        if len(configured_topic_ids) == 1:
            for t in course_topics:
                if t.id == configured_topic_ids[0]:
                    return t
            return course_topics[0]

        # Scope eligible topics
        if configured_topic_ids:
            eligible_topics = [t for t in course_topics if t.id in configured_topic_ids]
            if not eligible_topics:
                eligible_topics = course_topics
        else:
            eligible_topics = course_topics

        if len(eligible_topics) == 1:
            return eligible_topics[0]

        # Analyze current session topic distribution
        session_topic_counts: dict[uuid.UUID, int] = {}
        last_topic_id: uuid.UUID | None = None
        consecutive_same_topic = 0

        for a in session_answers:
            if a.question and a.question.topic_id:
                tid = a.question.topic_id
                session_topic_counts[tid] = session_topic_counts.get(tid, 0) + 1
                if last_topic_id == tid:
                    consecutive_same_topic += 1
                else:
                    consecutive_same_topic = 1
                last_topic_id = tid

        # Avoid staying stuck on the same topic for more than 2 consecutive questions
        candidate_pool = list(eligible_topics)
        if consecutive_same_topic >= 2 and last_topic_id is not None:
            others = [t for t in candidate_pool if t.id != last_topic_id]
            if others:
                candidate_pool = others

        # Fetch student historical performance for topic prioritization
        history = await cls.get_student_topic_performance(db, session.student_id, session.course_id)

        # Merge in-session scores for current topic performance
        topic_scores: dict[uuid.UUID, list[float]] = {}
        for a in session_answers:
            if a.question and a.question.topic_id:
                sc = (
                    a.fused_score
                    if a.fused_score is not None
                    else (a.llm_score if a.llm_score is not None else a.embedding_score)
                )
                if sc is not None:
                    topic_scores.setdefault(a.question.topic_id, []).append(float(sc))

        def topic_priority_key(topic: Topic) -> tuple[int, float, int]:
            h_data = history.get(topic.id)
            s_scores = topic_scores.get(topic.id, [])
            combined_scores = (h_data.get("scores", []) if h_data else []) + s_scores

            if combined_scores:
                avg = sum(combined_scores) / len(combined_scores)
            else:
                avg = 0.65  # Neutral baseline for untested topics

            # Tier 0: Weak (< 0.60)
            # Tier 1: Developing (0.60 to 0.74) or Untested
            # Tier 2: Strong (>= 0.75)
            if combined_scores and avg < 0.60:
                tier = 0
            elif not combined_scores or avg < 0.75:
                tier = 1
            else:
                tier = 2

            # Periodic retention check: if candidate has completed >= 2 questions on weak topics,
            # allow strong topics to be tested
            session_count = session_topic_counts.get(topic.id, 0)
            return (tier, avg, session_count)

        sorted_candidates = sorted(candidate_pool, key=topic_priority_key)
        return sorted_candidates[0] if sorted_candidates else eligible_topics[0]

    @classmethod
    async def select_adaptive_question(
        cls,
        db: AsyncSession,
        session: VivaSession,
        topic: Topic,
        target_difficulty: QuestionDifficulty,
        exclude_question_ids: set[uuid.UUID],
    ) -> Question | None:
        """Select a question matching topic and difficulty, avoiding intra-session and cross-session repetition."""
        # 1. Gather questions previously attempted by this student across earlier sessions in this course
        attempted_query = (
            select(Answer.question_id)
            .join(VivaSession, Answer.session_id == VivaSession.id)
            .where(
                VivaSession.student_id == session.student_id,
                VivaSession.course_id == session.course_id,
                VivaSession.id != session.id,
            )
        )
        attempted_result = await db.execute(attempted_query)
        previously_attempted_ids = set(attempted_result.scalars().all())

        # 2. Difficulty fallback hierarchy
        difficulty_order = [target_difficulty]
        if target_difficulty == QuestionDifficulty.EASY:
            difficulty_order.extend([QuestionDifficulty.MEDIUM, QuestionDifficulty.HARD])
        elif target_difficulty == QuestionDifficulty.HARD:
            difficulty_order.extend([QuestionDifficulty.MEDIUM, QuestionDifficulty.EASY])
        else:
            difficulty_order.extend([QuestionDifficulty.EASY, QuestionDifficulty.HARD])

        # Try to find a question in the preferred topic across fallback difficulties
        for diff in difficulty_order:
            q_stmt = select(Question).where(
                Question.topic_id == topic.id,
                Question.difficulty == diff,
                Question.is_approved.is_(True),
            )
            if exclude_question_ids:
                q_stmt = q_stmt.where(Question.id.not_in(exclude_question_ids))

            candidates = (
                (
                    await db.execute(
                        q_stmt.order_by(Question.times_used.asc(), Question.created_at.asc())
                    )
                )
                .scalars()
                .all()
            )
            if not candidates:
                continue

            # Prefer questions the student hasn't seen in past sessions
            unseen = [q for q in candidates if q.id not in previously_attempted_ids]
            if unseen:
                return unseen[0]
            # Fallback to least recently used question among candidates
            return candidates[0]

        # 3. If topic has no questions at any difficulty, attempt other permitted course topics
        config = session.config or {}
        configured_topic_ids = [uuid.UUID(str(tid)) for tid in config.get("topic_ids", []) if tid]

        fallback_topic_stmt = select(Topic).where(
            Topic.course_id == session.course_id, Topic.id != topic.id
        )
        if configured_topic_ids:
            fallback_topic_stmt = fallback_topic_stmt.where(Topic.id.in_(configured_topic_ids))

        other_topics = (
            (await db.execute(fallback_topic_stmt.order_by(Topic.sort_order))).scalars().all()
        )
        for alt_topic in other_topics:
            for diff in difficulty_order:
                q_stmt = select(Question).where(
                    Question.topic_id == alt_topic.id,
                    Question.difficulty == diff,
                    Question.is_approved.is_(True),
                )
                if exclude_question_ids:
                    q_stmt = q_stmt.where(Question.id.not_in(exclude_question_ids))

                candidates = (
                    (
                        await db.execute(
                            q_stmt.order_by(Question.times_used.asc(), Question.created_at.asc())
                        )
                    )
                    .scalars()
                    .all()
                )
                if candidates:
                    unseen = [q for q in candidates if q.id not in previously_attempted_ids]
                    return unseen[0] if unseen else candidates[0]

        return None

    @classmethod
    async def get_next_adaptive_question(
        cls,
        db: AsyncSession,
        session: VivaSession,
    ) -> Question | None:
        """Orchestrate next adaptive question selection based on answers submitted so far."""
        # 1. Fetch current session answers
        ans_result = await db.execute(
            select(Answer)
            .options(selectinload(Answer.question).selectinload(Question.topic))
            .where(Answer.session_id == session.id)
            .order_by(Answer.sequence_number)
        )
        answers = list(ans_result.scalars().all())

        # 2. Collect session score progression
        session_scores: list[float] = []
        for a in answers:
            sc = (
                a.fused_score
                if a.fused_score is not None
                else (a.llm_score if a.llm_score is not None else a.embedding_score)
            )
            if sc is not None:
                session_scores.append(float(sc))

        # 3. Fetch course topics
        topics_result = await db.execute(
            select(Topic).where(Topic.course_id == session.course_id).order_by(Topic.sort_order)
        )
        course_topics = list(topics_result.scalars().all())
        if not course_topics:
            return None

        # 4. Select next topic
        chosen_topic = await cls.select_next_topic(db, session, course_topics, answers)
        if chosen_topic is None:
            return None

        # 5. Determine target difficulty
        config = dict(session.config or {})
        base_difficulty = config.get("difficulty") or "medium"
        progression = list(config.get("difficulty_progression", []))

        # Look at last known difficulty if available, else baseline
        current_diff_str = progression[-1] if progression else base_difficulty
        next_difficulty = cls.compute_next_difficulty(current_diff_str, session_scores)

        # 6. Select question avoiding duplicates
        asked_ids = {uuid.UUID(str(qid)) for qid in config.get("asked_question_ids", []) if qid}
        for a in answers:
            if a.question_id:
                asked_ids.add(a.question_id)

        question = await cls.select_adaptive_question(
            db=db,
            session=session,
            topic=chosen_topic,
            target_difficulty=next_difficulty,
            exclude_question_ids=asked_ids,
        )

        if question is not None:
            # Update session config with decision metadata
            progression.append(question.difficulty.value)
            config["difficulty_progression"] = progression
            config["current_adaptive_difficulty"] = question.difficulty.value
            config["current_adaptive_topic_id"] = str(chosen_topic.id)
            config["current_adaptive_topic_name"] = chosen_topic.name

            # Add to asked question ids
            asked_list = list(config.get("asked_question_ids", []))
            if str(question.id) not in asked_list:
                asked_list.append(str(question.id))
            config["asked_question_ids"] = asked_list

            # Track topics practiced
            topics_practiced = list(config.get("topics_practiced", []))
            if chosen_topic.name not in topics_practiced:
                topics_practiced.append(chosen_topic.name)
            config["topics_practiced"] = topics_practiced

            session.config = config
            await db.commit()

        return question

    @classmethod
    async def generate_session_summary(
        cls,
        db: AsyncSession,
        session: VivaSession,
    ) -> dict[str, Any]:
        """Generate a learning summary for the completed adaptive session."""
        ans_result = await db.execute(
            select(Answer)
            .options(selectinload(Answer.question).selectinload(Question.topic))
            .where(Answer.session_id == session.id)
            .order_by(Answer.sequence_number)
        )
        answers = list(ans_result.scalars().all())

        config = session.config or {}
        difficulty_progression = list(config.get("difficulty_progression", []))
        if not difficulty_progression and answers:
            difficulty_progression = [
                a.question.difficulty.value for a in answers if a.question and a.question.difficulty
            ]

        topic_stats: dict[uuid.UUID, dict[str, Any]] = {}
        for a in answers:
            if not a.question or not a.question.topic:
                continue
            topic = a.question.topic
            sc = (
                a.fused_score
                if a.fused_score is not None
                else (a.llm_score if a.llm_score is not None else a.embedding_score)
            )
            if sc is None:
                continue

            rubric = a.rubric_breakdown or {}
            if topic.id not in topic_stats:
                topic_stats[topic.id] = {
                    "topic_id": str(topic.id),
                    "topic_name": topic.name,
                    "scores": [],
                    "rubrics": [],
                }
            topic_stats[topic.id]["scores"].append(float(sc))
            topic_stats[topic.id]["rubrics"].append(rubric)

        topics_practiced = []
        topics_showing_improvement = []
        topics_needing_attention = []
        has_multi_turn_topic = False

        for _t_id, data in topic_stats.items():
            sc = data["scores"]
            avg = round(sum(sc) / len(sc), 4)
            initial_score = sc[0]
            final_score = sc[-1]
            delta = round(final_score - initial_score, 4)

            entry = {
                "topic_id": data["topic_id"],
                "topic_name": data["topic_name"],
                "questions_count": len(sc),
                "average_score": avg,
                "average_score_percent": f"{round(avg * 100)}%",
                "initial_score_percent": f"{round(initial_score * 100)}%",
                "final_score_percent": f"{round(final_score * 100)}%",
            }
            topics_practiced.append(entry)

            if len(sc) >= 2:
                has_multi_turn_topic = True
                if delta >= 0.10:
                    topics_showing_improvement.append(
                        {
                            "topic_id": data["topic_id"],
                            "topic_name": data["topic_name"],
                            "initial_score_percent": f"{round(initial_score * 100)}%",
                            "final_score_percent": f"{round(final_score * 100)}%",
                            "delta_percent": f"+{round(delta * 100)}%",
                            "insight": "Demonstrated stronger key concept coverage on follow-up questions.",
                        }
                    )

            # Check if topic needs attention (average < 60% or final answer < 60%)
            if avg < 0.60 or final_score < 0.60:
                # Determine primary gap from rubrics
                comp_scores = [
                    r.get("completeness")
                    for r in data["rubrics"]
                    if isinstance(r.get("completeness"), (int, float))
                ]
                corr_scores = [
                    r.get("correctness")
                    for r in data["rubrics"]
                    if isinstance(r.get("correctness"), (int, float))
                ]
                gap = "core conceptual principles"
                if comp_scores and corr_scores:
                    if sum(comp_scores) < sum(corr_scores):
                        gap = "completeness (missing key syllabus concepts)"
                    else:
                        gap = "conceptual accuracy and precision"

                topics_needing_attention.append(
                    {
                        "topic_id": data["topic_id"],
                        "topic_name": data["topic_name"],
                        "average_score_percent": f"{round(avg * 100)}%",
                        "gap": gap,
                        "recommendation": f"Focus on {gap} during your next practice session.",
                    }
                )

        # Suggest next topics: weak topics first, else unpracticed course topics
        course_topics = (
            (await db.execute(select(Topic).where(Topic.course_id == session.course_id)))
            .scalars()
            .all()
        )
        practiced_topic_ids = set(topic_stats.keys())

        suggested_next_topics = []
        for t_need in topics_needing_attention:
            suggested_next_topics.append(
                {
                    "topic_id": t_need["topic_id"],
                    "topic_name": t_need["topic_name"],
                    "reason": f"Reinforce {t_need['gap']}.",
                    "priority": "high",
                }
            )

        for ct in course_topics:
            if ct.id not in practiced_topic_ids and len(suggested_next_topics) < 3:
                suggested_next_topics.append(
                    {
                        "topic_id": str(ct.id),
                        "topic_name": ct.name,
                        "reason": "Explore new syllabus concepts to broaden your practice coverage.",
                        "priority": "normal",
                    }
                )

        insufficient_data_note = None
        if not has_multi_turn_topic:
            insufficient_data_note = (
                "Insufficient repeat turns per topic to establish intra-session score progression. "
                "Topics practiced once are classified based on current performance."
            )

        summary = {
            "is_adaptive": True,
            "session_id": str(session.id),
            "topics_practiced": topics_practiced,
            "difficulty_progression": difficulty_progression,
            "topics_showing_improvement": topics_showing_improvement,
            "topics_needing_attention": topics_needing_attention,
            "suggested_next_topics": suggested_next_topics,
            "insufficient_data_note": insufficient_data_note,
            "generated_at": datetime.now(UTC).isoformat(),
        }

        # Persist summary inside session config
        config = dict(session.config or {})
        config["adaptive_summary"] = summary
        session.config = config
        await db.commit()

        return summary
