import pytest

@pytest.fixture
def minimal_valid_record():
    return {
        "id": "rec_001",
        "prompt": "இது ஒரு சோதனை கேள்வி?",
        "response": "ஆம், இது ஒரு சோதனை பதில்.",
        "register": "spoken_colloquial",
        "region": "Generic Tamil Nadu",
        "domain": "everyday",
        "task_type": "qa"
    }

@pytest.fixture
def spoken_record():
    return {
        "id": "spoken_001",
        "prompt": "எப்படி இருக்கீங்க?",
        "response": "நல்லா இருக்கேன், நீங்க?",
        "register": "spoken_colloquial",
        "region": "Generic Tamil Nadu",
        "domain": "everyday",
        "task_type": "qa"
    }

@pytest.fixture
def formal_record():
    return {
        "id": "formal_001",
        "prompt": "நீங்கள் எப்படி இருக்கிறீர்கள்?",
        "response": "நான் நன்றாக உள்ளேன், நீங்கள் எப்படி இருக்கிறீர்கள்?",
        "register": "modern_formal",
        "region": "Generic Tamil Nadu",
        "domain": "everyday",
        "task_type": "qa"
    }

@pytest.fixture
def literary_record():
    return {
        "id": "literary_001",
        "prompt": "நீர் எங்ஙனம் உள்ளீர்?",
        "response": "யான் நலம், நீர் எங்ஙனம் உள்ளீர்?",
        "register": "literary_prose",
        "region": "Generic Tamil Nadu",
        "domain": "everyday",
        "task_type": "qa"
    }
