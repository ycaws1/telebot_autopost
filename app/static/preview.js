(() => {
  const caption = document.getElementById("caption");
  const media = document.getElementById("media");
  const channel = document.getElementById("channel_id");
  const previewCaption = document.getElementById("preview-caption");
  const previewMedia = document.getElementById("preview-media");
  const previewAuthor = document.getElementById("preview-author");
  const previewTime = document.getElementById("preview-time");
  const previewEmpty = document.getElementById("preview-empty");
  const tgMsg = document.getElementById("tg-msg");
  const scheduledAt = document.getElementById("scheduled_at");
  const scheduleNow = document.getElementById("schedule-now");
  const form = document.getElementById("post-form");
  const sendPreview = document.getElementById("send-preview");
  const formFlash = document.getElementById("form-flash");

  function showFlash(message, kind) {
    if (!formFlash) return;
    formFlash.hidden = !message;
    formFlash.textContent = message || "";
    formFlash.classList.remove("ok", "error");
    if (kind) formFlash.classList.add(kind);
  }

  if (sendPreview && form) {
    sendPreview.addEventListener("click", async () => {
      sendPreview.disabled = true;
      showFlash("Sending preview…", "ok");
      try {
        const body = new FormData(form);
        // Preview endpoint only needs caption/media/keep_media
        const res = await fetch("/posts/preview", {
          method: "POST",
          body,
          headers: { Accept: "application/json" },
          credentials: "same-origin",
        });
        const data = await res.json().catch(() => ({}));
        if (!res.ok || !data.ok) {
          showFlash(data.error || "Preview failed", "error");
        } else {
          showFlash("Preview sent to your Telegram DM. You can still Save.", "ok");
        }
      } catch (err) {
        showFlash("Preview failed (network error)", "error");
      } finally {
        sendPreview.disabled = false;
      }
    });
  }

  if (scheduleNow && scheduledAt) {
    scheduleNow.addEventListener("click", () => {
      const d = new Date();
      const pad = (n) => String(n).padStart(2, "0");
      scheduledAt.value = `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
      render();
    });
  }

  if (!caption || !previewCaption || !previewMedia) return;

  const objectUrls = [];

  function clearObjectUrls() {
    while (objectUrls.length) URL.revokeObjectURL(objectUrls.pop());
  }

  function formatTime(value) {
    const d = value ? new Date(value) : new Date();
    if (Number.isNaN(d.getTime())) return "";
    return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  }

  function selectedChannelName() {
    if (!channel) return "Channel";
    const opt = channel.options[channel.selectedIndex];
    return (opt && opt.dataset.name) || "Channel";
  }

  function existingMedia() {
    return Array.from(document.querySelectorAll('input[name="keep_media"]:checked')).map((el) => ({
      type: el.dataset.mediaType === "video" ? "video" : "photo",
      url: el.dataset.mediaUrl,
      revoke: false,
    }));
  }

  function newMedia() {
    const files = media && media.files ? Array.from(media.files) : [];
    return files.map((file) => {
      const url = URL.createObjectURL(file);
      objectUrls.push(url);
      return {
        type: file.type.startsWith("video/") ? "video" : "photo",
        url,
        revoke: true,
      };
    });
  }

  function albumClass(count) {
    if (count <= 1) return "album-1";
    if (count === 2) return "album-2";
    if (count === 3) return "album-3";
    if (count === 4) return "album-4";
    if (count <= 6) return "album-6";
    if (count <= 9) return "album-9";
    return "album-10";
  }

  function render() {
    clearObjectUrls();
    const text = (caption.value || "").trim();
    const items = [...existingMedia(), ...newMedia()].slice(0, 10);
    const hasContent = text.length > 0 || items.length > 0;

    previewAuthor.textContent = selectedChannelName();
    previewTime.textContent = formatTime(scheduledAt && scheduledAt.value);
    previewCaption.textContent = text;
    previewCaption.hidden = !text;
    previewEmpty.hidden = hasContent;
    tgMsg.hidden = !hasContent;
    tgMsg.classList.toggle("text-only", items.length === 0 && text.length > 0);
    tgMsg.classList.toggle("media-post", items.length > 0);

    previewMedia.innerHTML = "";
    if (!items.length) {
      previewMedia.hidden = true;
      previewMedia.className = "tg-media";
      return;
    }

    previewMedia.hidden = false;
    previewMedia.className = `tg-media ${albumClass(items.length)}`;
    items.forEach((item, index) => {
      const cell = document.createElement("div");
      cell.className = "tg-cell";
      if (item.type === "video") {
        const v = document.createElement("video");
        v.src = item.url;
        v.muted = true;
        v.playsInline = true;
        v.setAttribute("preload", "metadata");
        cell.appendChild(v);
        const badge = document.createElement("span");
        badge.className = "tg-video-badge";
        badge.textContent = "▶";
        cell.appendChild(badge);
      } else {
        const img = document.createElement("img");
        img.src = item.url;
        img.alt = `media ${index + 1}`;
        cell.appendChild(img);
      }
      previewMedia.appendChild(cell);
    });
  }

  caption.addEventListener("input", render);
  if (media) media.addEventListener("change", render);
  if (channel) channel.addEventListener("change", render);
  if (scheduledAt) scheduledAt.addEventListener("change", render);
  document.querySelectorAll('input[name="keep_media"]').forEach((el) => {
    el.addEventListener("change", render);
  });
  render();
})();
