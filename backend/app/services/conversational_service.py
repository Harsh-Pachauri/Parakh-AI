"""Conversational service for humanized, empathetic viva dialogue, transitions, and greetings."""

from __future__ import annotations

import random


class ConversationalService:
    """Provides natural, empathetic, context-aware dialogue for oral examinations."""

    # 1. Empathetic Acknowledgements based on actual evaluated score
    STRONG_ACKNOWLEDGEMENTS = [
        "Well explained! You've got the core idea.",
        "Great response. You covered the key points clearly.",
        "Nicely explained. You demonstrated clear understanding.",
        "Good explanation. That captures the main concept well.",
    ]

    PARTIAL_ACKNOWLEDGEMENTS = [
        "You're on the right track. Let's build on that.",
        "Good effort. You touched on the main idea, with just a couple of details to sharpen.",
        "You've got the basic concept in place. Let's keep exploring.",
        "Solid attempt. There's a good foundation here to refine.",
    ]

    DEVELOPING_ACKNOWLEDGEMENTS = [
        "No worries, this is a tricky concept. Let's use it as a learning opportunity.",
        "That's a tough one. Oral exams are all about finding where to focus next.",
        "Good try. Concepts like this often take a few attempts to really click.",
        "Thanks for giving that a shot. Don't worry about getting everything perfect.",
    ]

    UNCLEAR_ACKNOWLEDGEMENTS = [
        "I see what you're trying to explain. Let's keep moving forward.",
        "Thanks for explaining your thought process.",
    ]

    # 2. Conversational Transitions between questions
    STEPPING_UP_TRANSITIONS = [
        "You handled that well. Let's try one that's a little more challenging.",
        "Solid grasp. Let's take it a step further.",
        "Nice momentum. Let's see how you approach this next one.",
    ]

    FOUNDATIONAL_TRANSITIONS = [
        "Let's look at a foundational concept to make this clearer.",
        "Let's take a step back and explore the core principle behind this.",
        "No problem at all. Let's look at this from a foundational perspective.",
    ]

    TOPIC_SHIFT_TRANSITIONS = [
        "Alright, let's explore another part of the syllabus.",
        "Let's shift gears and look at another concept.",
        "Okay, let's move to a different topic in your course.",
    ]

    SAME_TOPIC_TRANSITIONS = [
        "Nice, let's build on that idea.",
        "Okay, let's look at this from another angle.",
        "Let's stay with this topic for another question.",
    ]

    REVISITING_TRANSITIONS = [
        "Let's revisit an idea that could use a little more practice.",
        "Here is a concept to check your understanding on.",
    ]

    # 3. Viva Openings
    PRACTICE_OPENINGS = [
        "Welcome to your viva practice{name_prefix}. Take a breath, relax, and answer in your own words.",
        "Hey{name_prefix}! We'll go through a few questions together. Take your time and explain your thinking.",
        "Ready{name_prefix}? Let's start with a warm-up question to get your thoughts flowing.",
        "Welcome{name_prefix}! Don't worry about getting every detail perfect. Let's learn as we go.",
    ]

    ASSESSMENT_OPENINGS = [
        "Welcome to your viva examination{name_prefix}. Take your time with each question and explain your reasoning clearly.",
        "Welcome{name_prefix}. We will proceed through the questions for this assessment. Answer when you are ready.",
    ]

    # 4. Session Closings
    CLOSINGS_HIGH = [
        "Outstanding work{name_prefix}! You demonstrated strong mastery across these concepts. Your detailed report is ready below.",
        "Well done{name_prefix}! You articulated your understanding with clarity and confidence. Take a look at your summary below.",
    ]

    CLOSINGS_MID = [
        "Good session{name_prefix}! You've got solid foundations, and the breakdown below highlights a few specific areas to polish.",
        "Nice progress today{name_prefix}! Keep practicing, and you'll build even more confidence with these concepts.",
    ]

    CLOSINGS_DEVELOPING = [
        "Good work showing up{name_prefix} and giving it your best try. Review the suggestions in your report below and come back when you're ready for another round.",
        "You've made a great start{name_prefix}. Review the highlighted topics in your report and revisit them whenever you're ready.",
    ]

    @classmethod
    def get_empathetic_acknowledgement(
        cls,
        score: float | None,
        transcript: str | None = None,
        is_followup: bool = False,
    ) -> str:
        """Return an acknowledgement strictly aligned with the evaluated answer score."""
        clean_text = (transcript or "").strip()
        if len(clean_text) < 15:
            return random.choice(cls.UNCLEAR_ACKNOWLEDGEMENTS)

        if score is None:
            return "Thank you for explaining your answer."

        if score >= 0.75:
            return random.choice(cls.STRONG_ACKNOWLEDGEMENTS)
        elif score >= 0.50:
            return random.choice(cls.PARTIAL_ACKNOWLEDGEMENTS)
        else:
            return random.choice(cls.DEVELOPING_ACKNOWLEDGEMENTS)

    @classmethod
    def get_conversational_transition(
        cls,
        prev_difficulty: str | None,
        next_difficulty: str | None,
        is_same_topic: bool,
        is_revisiting: bool = False,
        score: float | None = None,
    ) -> str:
        """Return a natural bridge phrase leading into the next question."""
        prev_d = str(prev_difficulty or "medium").lower()
        next_d = str(next_difficulty or "medium").lower()

        # 1. Stepping up difficulty
        if (prev_d == "easy" and next_d in ("medium", "hard")) or (
            prev_d == "medium" and next_d == "hard"
        ):
            if score is not None and score >= 0.70:
                return random.choice(cls.STEPPING_UP_TRANSITIONS)

        # 2. Stepping down difficulty to foundational level
        if (prev_d == "hard" and next_d in ("medium", "easy")) or (
            prev_d == "medium" and next_d == "easy"
        ):
            return random.choice(cls.FOUNDATIONAL_TRANSITIONS)

        # 3. Revisiting a previously weak topic
        if is_revisiting:
            return random.choice(cls.REVISITING_TRANSITIONS)

        # 4. Same topic continuation
        if is_same_topic:
            return random.choice(cls.SAME_TOPIC_TRANSITIONS)

        # 5. Topic change
        return random.choice(cls.TOPIC_SHIFT_TRANSITIONS)

    @classmethod
    def get_viva_opening(
        cls,
        student_name: str | None = None,
        is_adaptive: bool = True,
        assessment_title: str | None = None,
    ) -> str:
        """Generate a warm, natural introductory greeting before the first question."""
        first_name = (
            student_name.strip().split()[0] if student_name and student_name.strip() else None
        )
        name_prefix = f", {first_name}" if first_name else ""

        if not is_adaptive and assessment_title:
            prefix = f"Welcome to {assessment_title}{name_prefix}."
            return f"{prefix} Take your time with each question and explain your thinking in your own words."

        template = random.choice(cls.PRACTICE_OPENINGS)
        return template.format(name_prefix=name_prefix)

    @classmethod
    def get_session_closing_message(
        cls,
        total_score: float | None,
        student_name: str | None = None,
        answer_count: int = 0,
    ) -> str:
        """Generate a supportive, grounded closing message based on session score."""
        first_name = (
            student_name.strip().split()[0] if student_name and student_name.strip() else None
        )
        name_prefix = f", {first_name}" if first_name else ""

        if total_score is None or answer_count == 0:
            return f"That concludes our session{name_prefix}. Your practice feedback is ready."

        if total_score >= 0.75:
            template = random.choice(cls.CLOSINGS_HIGH)
        elif total_score >= 0.50:
            template = random.choice(cls.CLOSINGS_MID)
        else:
            template = random.choice(cls.CLOSINGS_DEVELOPING)

        return template.format(name_prefix=name_prefix)
