import pytest

from app.telegram_client import MediaItem, TelegramError, send_post


class FakeClient:
    def __init__(self):
        self.calls = []

    async def post(self, url, data=None, files=None):
        self.calls.append((url, data, files))

        class R:
            def raise_for_status(self):
                pass

            def json(self):
                return {"ok": True, "result": {}}

        return R()


@pytest.mark.asyncio
async def test_send_text_only():
    fake = FakeClient()
    await send_post("@ch", "hello", [], bot_token="T", client=fake)
    assert "sendMessage" in fake.calls[0][0]
    assert fake.calls[0][1]["text"] == "hello"


@pytest.mark.asyncio
async def test_send_single_photo(tmp_path):
    p = tmp_path / "a.jpg"
    p.write_bytes(b"img")
    fake = FakeClient()
    await send_post("@ch", "cap", [MediaItem("photo", p)], bot_token="T", client=fake)
    assert "sendPhoto" in fake.calls[0][0]


@pytest.mark.asyncio
async def test_reject_more_than_ten(tmp_path):
    items = []
    for i in range(11):
        f = tmp_path / f"{i}.jpg"
        f.write_bytes(b"x")
        items.append(MediaItem("photo", f))
    with pytest.raises(TelegramError, match="10"):
        await send_post("@ch", "c", items, bot_token="T", client=object())


@pytest.mark.asyncio
async def test_text_only_requires_caption():
    with pytest.raises(TelegramError, match="caption"):
        await send_post("@ch", "  ", [], bot_token="T", client=object())
