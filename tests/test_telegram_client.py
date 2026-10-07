import pytest

from app.telegram_client import MediaItem, TelegramError, publish_post, send_post


class FakeClient:
    def __init__(self):
        self.calls = []
        self._n = 0

    async def post(self, url, data=None, files=None):
        self.calls.append((url, data, files))
        self._n += 1
        mid = self._n

        class R:
            def raise_for_status(self):
                pass

            def json(self):
                if "sendMediaGroup" in url:
                    return {
                        "ok": True,
                        "result": [{"message_id": mid}, {"message_id": mid + 1}],
                    }
                return {"ok": True, "result": {"message_id": mid}}

        return R()


@pytest.mark.asyncio
async def test_send_text_only():
    fake = FakeClient()
    ids = await send_post("@ch", "hello", [], bot_token="T", client=fake)
    assert "sendMessage" in fake.calls[0][0]
    assert fake.calls[0][1]["text"] == "hello"
    assert ids == [1]


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


@pytest.mark.asyncio
async def test_publish_sends_to_staging_then_forwards():
    fake = FakeClient()
    await publish_post(
        "@channel",
        "hello",
        [],
        staging_chat_id="999",
        bot_token="T",
        client=fake,
        cleanup_staging=True,
    )
    urls = [c[0] for c in fake.calls]
    assert any("sendMessage" in u for u in urls)
    assert any("forwardMessage" in u for u in urls)
    assert any("deleteMessage" in u for u in urls)
    send_call = next(c for c in fake.calls if "sendMessage" in c[0])
    assert send_call[1]["chat_id"] == "999"
    fwd = next(c for c in fake.calls if "forwardMessage" in c[0])
    assert fwd[1]["chat_id"] == "@channel"
    assert fwd[1]["from_chat_id"] == "999"
