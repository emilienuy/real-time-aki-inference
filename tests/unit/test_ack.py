from src.ack import build_ack


def test_build_ack_contains_msh_and_msa():
    ack = build_ack()
    text = ack.decode("ascii")

    assert "MSH|" in text
    assert "MSA|AA" in text