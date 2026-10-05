(() => {
  const caption = document.getElementById("caption");
  const media = document.getElementById("media");
  const previewCaption = document.getElementById("preview-caption");
  const previewThumbs = document.getElementById("preview-thumbs");
  if (!caption || !previewCaption || !previewThumbs) return;

  const urls = [];

  function clearUrls() {
    while (urls.length) URL.revokeObjectURL(urls.pop());
  }

  function render() {
    previewCaption.textContent = caption.value || "";
    clearUrls();
    previewThumbs.innerHTML = "";
    const files = media && media.files ? Array.from(media.files) : [];
    files.forEach((file) => {
      const url = URL.createObjectURL(file);
      urls.push(url);
      if (file.type.startsWith("video/")) {
        const v = document.createElement("video");
        v.src = url;
        v.muted = true;
        previewThumbs.appendChild(v);
      } else {
        const img = document.createElement("img");
        img.src = url;
        img.alt = file.name;
        previewThumbs.appendChild(img);
      }
    });
  }

  caption.addEventListener("input", render);
  if (media) media.addEventListener("change", render);
  render();
})();
