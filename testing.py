import question


async def test_question(q, a):
    await question.answer_question(q, a)