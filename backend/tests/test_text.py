from app.utils.text import clean_transcript


def test_clean_transcript_preserves_candidate_word_casing() -> None:
    assert (
        clean_transcript("breadth first search visits each level and uses a queue")
        == "Breadth first search visits each level and uses a queue."
    )


def test_clean_transcript_capitalizes_sentence_starts_and_removes_fillers() -> None:
    assert clean_transcript("um queues are useful. uh stacks reverse order") == (
        "Queues are useful. Stacks reverse order."
    )


def test_clean_transcript_preserves_meaningful_speech_words() -> None:
    assert clean_transcript("I would like to explain it basically") == (
        "I would like to explain it basically."
    )
