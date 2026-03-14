// Theme Toggle
function toggleTheme() {
  const html = document.documentElement;
  const isDark = html.getAttribute('data-theme') === 'dark';
  html.setAttribute('data-theme', isDark ? 'light' : 'dark');
  localStorage.setItem('theme', isDark ? 'light' : 'dark');
  document.getElementById('theme-icon').className = isDark ? 'fas fa-moon' : 'fas fa-sun';
}

(function () {
  const saved = localStorage.getItem('theme') || 'light';
  document.documentElement.setAttribute('data-theme', saved);
  const icon = document.getElementById('theme-icon');
  if (icon) icon.className = saved === 'dark' ? 'fas fa-sun' : 'fas fa-moon';
})();

// Mobile Menu
function toggleMobileMenu() {
  document.getElementById('mobileMenu')?.classList.toggle('open');
}

// Auto-dismiss flash messages
setTimeout(() => {
  document.querySelectorAll('.flash').forEach(el => {
    el.style.opacity = '0'; el.style.transform = 'translateX(100%)';
    setTimeout(() => el.remove(), 300);
  });
}, 5000);

// CSRF helper (kept for any future form use)
function getCsrf() {
  return document.querySelector('meta[name="csrf-token"]')?.content || '';
}

// OTP auto-focus
document.querySelectorAll('.otp-input').forEach((input, i, inputs) => {
  input.addEventListener('input', () => {
    if (input.value.length === 1 && inputs[i + 1]) inputs[i + 1].focus();
  });
  input.addEventListener('keydown', (e) => {
    if (e.key === 'Backspace' && !input.value && inputs[i - 1]) inputs[i - 1].focus();
  });
});

// Collect OTP digits before submit
document.querySelector('.otp-form')?.addEventListener('submit', function () {
  const digits = Array.from(document.querySelectorAll('.otp-input')).map(i => i.value).join('');
  const hidden = document.getElementById('otp-hidden');
  if (hidden) hidden.value = digits;
});

// Image upload in editor
function insertImage() {
  const input = document.createElement('input');
  input.type = 'file'; input.accept = 'image/*';
  input.onchange = () => {
    const file = input.files[0]; if (!file) return;
    const fd = new FormData(); fd.append('image', file);
    fetch('/upload-image', { method: 'POST', body: fd })
      .then(r => r.json()).then(data => {
        const ta = document.getElementById('content-editor');
        if (ta) insertAtCursor(ta, `\n![Image](${data.url})\n`);
      });
  };
  input.click();
}

function insertAtCursor(el, text) {
  const s = el.selectionStart, e = el.selectionEnd;
  el.value = el.value.slice(0, s) + text + el.value.slice(e);
  el.selectionStart = el.selectionEnd = s + text.length;
  el.focus();
}

function wrapText(before, after) {
  const ta = document.getElementById('content-editor'); if (!ta) return;
  const s = ta.selectionStart, e = ta.selectionEnd;
  const sel = ta.value.slice(s, e) || 'text';
  const wrapped = before + sel + after;
  ta.value = ta.value.slice(0, s) + wrapped + ta.value.slice(e);
  ta.selectionStart = s + before.length;
  ta.selectionEnd = s + before.length + sel.length;
  ta.focus();
}

// Share blog
function shareBlog(title, url) {
  if (navigator.share) {
    navigator.share({ title, url });
  } else {
    navigator.clipboard.writeText(url);
    showToast('Link copied!');
  }
}

function showToast(msg) {
  const t = document.createElement('div');
  t.className = 'flash flash-success';
  t.innerHTML = `<span>${msg}</span>`;
  t.style.cssText = 'position:fixed;bottom:1rem;right:1rem;z-index:999;';
  document.body.appendChild(t);
  setTimeout(() => t.remove(), 2500);
}

// Reply toggle
document.addEventListener('click', function (e) {
  const btn = e.target.closest('[data-reply-to]');
  if (!btn) return;
  const replyId = btn.dataset.replyTo;
  document.querySelectorAll('.reply-form').forEach(f => f.classList.add('hidden'));
  const form = document.getElementById(`reply-form-${replyId}`);
  if (form) form.classList.toggle('hidden');
});

// Edit comment toggle
document.addEventListener('click', function (e) {
  const btn = e.target.closest('[data-edit-comment]');
  if (!btn) return;
  const id = btn.dataset.editComment;
  document.getElementById(`edit-form-${id}`)?.classList.toggle('hidden');
});
