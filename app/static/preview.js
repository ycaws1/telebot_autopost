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
  const queueEl = document.getElementById("media-queue");
  const seedEl = document.getElementById("media-queue-seed");

  /** @type {{kind:'existing'|'file', id?:number, file?:File, type:string, name:string, url:string}[]} */
  let queue = [];
  const objectUrls = [];

  function showFlash(message, kind) {
    if (!formFlash) return;
    formFlash.hidden = !message;
    formFlash.textContent = message || "";
    formFlash.classList.remove("ok", "error");
    if (kind) formFlash.classList.add(kind);
  }

  function clearObjectUrls() {
    while (objectUrls.length) URL.revokeObjectURL(objectUrls.pop());
  }

  function revokeQueueUrls() {
    queue.forEach((item) => {
      if (item.kind === "file" && item.url) URL.revokeObjectURL(item.url);
    });
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

  function mediaTypeFromName(name, mime) {
    if (mime && mime.startsWith("video/")) return "video";
    if (mime && mime.startsWith("image/")) return "photo";
    const lower = (name || "").toLowerCase();
    if (/\.(mp4|mov|m4v|webm|mkv)$/.test(lower)) return "video";
    return "photo";
  }

  function loadSeed() {
    if (!seedEl) return;
    queue = Array.from(seedEl.querySelectorAll("li")).map((el) => ({
      kind: "existing",
      id: Number(el.dataset.id),
      type: el.dataset.type === "video" ? "video" : "photo",
      name: el.dataset.name || String(el.dataset.id),
      url: el.dataset.url,
    }));
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

  function renderQueue() {
    if (!queueEl) return;
    if (!queue.length) {
      queueEl.innerHTML = '<li class="empty-hint">No media yet — add photos or videos below.</li>';
      return;
    }
    queueEl.innerHTML = queue
      .map((item, index) => {
        const label = esc(item.type) + " — " + esc(item.name);
        return (
          '<li class="media-queue-item" data-index="' +
          index +
          '">' +
          '<span class="media-queue-label">' +
          (index + 1) +
          ". " +
          label +
          "</span>" +
          '<span class="media-queue-actions">' +
          '<button type="button" class="secondary media-move" data-dir="-1" data-index="' +
          index +
          '" aria-label="Move up"' +
          (index === 0 ? " disabled" : "") +
          ">↑</button>" +
          '<button type="button" class="secondary media-move" data-dir="1" data-index="' +
          index +
          '" aria-label="Move down"' +
          (index === queue.length - 1 ? " disabled" : "") +
          ">↓</button>" +
          '<button type="button" class="danger-btn media-remove" data-index="' +
          index +
          '" aria-label="Remove">Remove</button>' +
          "</span></li>"
        );
      })
      .join("");
  }

  function esc(s) {
    return String(s ?? "").replace(/[&<>"']/g, (ch) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[ch])
    );
  }

  function renderPreview() {
    if (!caption || !previewCaption || !previewMedia) return;
    clearObjectUrls();
    const text = (caption.value || "").trim();
    const items = queue.slice(0, 10).map((item) => ({
      type: item.type,
      url: item.url,
    }));
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

  function render() {
    renderQueue();
    renderPreview();
  }

  function moveItem(index, dir) {
    const next = index + dir;
    if (next < 0 || next >= queue.length) return;
    const tmp = queue[index];
    queue[index] = queue[next];
    queue[next] = tmp;
    render();
  }

  function removeItem(index) {
    const item = queue[index];
    if (!item) return;
    if (item.kind === "file" && item.url) URL.revokeObjectURL(item.url);
    queue.splice(index, 1);
    render();
  }

  function addFiles(fileList) {
    const files = Array.from(fileList || []);
    if (!files.length) return;
    const room = 10 - queue.length;
    if (room <= 0) {
      showFlash("Maximum 10 media files per post", "error");
      return;
    }
    const accepted = files.slice(0, room);
    if (files.length > room) {
      showFlash("Only the first " + room + " file(s) were added (max 10).", "error");
    }
    accepted.forEach((file) => {
      const url = URL.createObjectURL(file);
      queue.push({
        kind: "file",
        file,
        type: mediaTypeFromName(file.name, file.type),
        name: file.name,
        url,
      });
    });
    if (media) media.value = "";
    render();
  }

  function syncFormFields() {
    form.querySelectorAll('input[name="keep_media"], input[name="media_order"]').forEach((el) =>
      el.remove()
    );
    if (media) {
      const dt = new DataTransfer();
      queue.forEach((item) => {
        if (item.kind === "file" && item.file) dt.items.add(item.file);
      });
      media.files = dt.files;
    }
    let newIndex = 0;
    queue.forEach((item) => {
      if (item.kind === "existing") {
        const keep = document.createElement("input");
        keep.type = "hidden";
        keep.name = "keep_media";
        keep.value = String(item.id);
        form.appendChild(keep);
        const order = document.createElement("input");
        order.type = "hidden";
        order.name = "media_order";
        order.value = "e:" + item.id;
        form.appendChild(order);
      } else if (item.file) {
        const order = document.createElement("input");
        order.type = "hidden";
        order.name = "media_order";
        order.value = "n:" + newIndex;
        form.appendChild(order);
        newIndex += 1;
      }
    });
  }

  function buildOrderedFormData() {
    syncFormFields();
    return new FormData(form);
  }

  if (queueEl) {
    queueEl.addEventListener("click", (ev) => {
      const btn = ev.target.closest("button");
      if (!btn) return;
      const index = Number(btn.dataset.index);
      if (Number.isNaN(index)) return;
      if (btn.classList.contains("media-move")) {
        moveItem(index, Number(btn.dataset.dir));
      } else if (btn.classList.contains("media-remove")) {
        removeItem(index);
      }
    });
  }

  if (form) {
    form.addEventListener("submit", () => {
      syncFormFields();
    });
  }

  if (sendPreview && form) {
    sendPreview.addEventListener("click", async () => {
      sendPreview.disabled = true;
      showFlash("Sending preview…", "ok");
      try {
        const body = buildOrderedFormData();
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

  if (caption) caption.addEventListener("input", renderPreview);
  if (media) media.addEventListener("change", () => addFiles(media.files));
  if (channel) channel.addEventListener("change", renderPreview);
  if (scheduledAt) scheduledAt.addEventListener("change", renderPreview);

  loadSeed();
  render();

  window.addEventListener("beforeunload", () => {
    revokeQueueUrls();
    clearObjectUrls();
  });
})();
