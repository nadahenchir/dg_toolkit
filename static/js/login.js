// login.js — DG Toolkit login page

function togglePassword() {
  const input = document.getElementById('password');
  const icon  = document.getElementById('eye-icon');
  if (input.type === 'password') {
    input.type = 'text';
    icon.innerHTML = `
      <path d="M2 2l12 12" stroke="currentColor" stroke-width="1.3" stroke-linecap="round"/>
      <path d="M6.5 6.7A2 2 0 0 0 8 10a2 2 0 0 0 1.5-.7" stroke="currentColor" stroke-width="1.3"/>
      <path d="M4.2 4.4C2.7 5.4 1.5 6.8 1 8c0 0 2.5 5 7 5 1.3 0 2.4-.4 3.4-1" stroke="currentColor" stroke-width="1.3"/>
      <path d="M9.9 3.6C9.3 3.2 8.7 3 8 3c-4.5 0-7 5-7 5 .3.5.6 1 1 1.5" stroke="currentColor" stroke-width="1.3"/>
    `;
  } else {
    input.type = 'password';
    icon.innerHTML = `
      <path d="M1 8C1 8 3.5 3 8 3s7 5 7 5-2.5 5-7 5-7-5-7-5z" stroke="currentColor" stroke-width="1.3"/>
      <circle cx="8" cy="8" r="2" stroke="currentColor" stroke-width="1.3"/>
    `;
  }
}

function clearErrors() {
  ['f-email', 'f-password'].forEach(id => {
    document.getElementById(id).classList.remove('error');
  });
  const alert = document.getElementById('login-alert');
  alert.style.display = 'none';
  alert.textContent = '';
}

function showAlert(msg) {
  const alert = document.getElementById('login-alert');
  alert.textContent = msg;
  alert.style.display = 'block';
}

function setLoading(loading) {
  const btn     = document.getElementById('login-btn');
  const text    = document.getElementById('login-btn-text');
  const spinner = document.getElementById('login-spinner');
  btn.disabled        = loading;
  text.style.display  = loading ? 'none' : 'inline';
  spinner.style.display = loading ? 'block' : 'none';
}

async function handleLogin() {
  clearErrors();

  const email    = document.getElementById('email').value.trim();
  const password = document.getElementById('password').value;

  let valid = true;
  if (!email || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
    document.getElementById('f-email').classList.add('error');
    valid = false;
  }
  if (!password) {
    document.getElementById('f-password').classList.add('error');
    valid = false;
  }
  if (!valid) return;

  setLoading(true);

  try {
    const res = await fetch('/api/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, password }),
    });

    const data = await res.json();

    if (!res.ok) {
      showAlert(data.error || 'Login failed. Please try again.');
      return;
    }

    // Redirect to dashboard
    window.location.href = '/dashboard';

  } catch (err) {
    showAlert('Network error. Please check your connection.');
  } finally {
    setLoading(false);
  }
}

// Allow Enter key to submit
document.addEventListener('keydown', (e) => {
  if (e.key === 'Enter') handleLogin();
});