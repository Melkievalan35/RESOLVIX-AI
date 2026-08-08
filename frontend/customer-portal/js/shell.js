/* Renders the sidebar + mobile topbar toggle into any authenticated page.
   Call Shell.mount('dashboard') etc. after Store.requireAuth(). */

const NAV_ITEMS = [
  { key: 'dashboard', href: 'dashboard.html', label: 'Dashboard', icon: 'M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-6 0a1 1 0 001-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 001 1m-6 0h6' },
  { key: 'new', href: 'complaint-form.html', label: 'File a Complaint', icon: 'M12 4v16m8-8H4' },
  { key: 'history', href: 'complaint-history.html', label: 'Complaint History', icon: 'M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-6 9l2 2 4-4' },
  { key: 'chat', href: 'chat-interface.html', label: 'Chat with Agent', icon: 'M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.86 9.86 0 01-4-.8L3 20l1.3-3.9A7.9 7.9 0 013 12c0-4.418 4.03-8 9-8s9 3.582 9 8z' },
  { key: 'profile', href: 'profile.html', label: 'Profile & Settings', icon: 'M5.121 17.804A13.937 13.937 0 0112 16c2.5 0 4.847.655 6.879 1.804M15 10a3 3 0 11-6 0 3 3 0 016 0zm6 2a9 9 0 11-18 0 9 9 0 0118 0z' },
];

const Shell = {
  mount(activeKey) {
    const user = Store.currentUser();
    if (!user) return;

    const sidebarMount = document.getElementById('sidebarMount');
    if (sidebarMount) {
      const links = NAV_ITEMS.map(item => `
        <a class="nav-link ${item.key === activeKey ? 'active' : ''}" href="${item.href}">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="${item.icon}"/></svg>
          ${item.label}
        </a>`).join('');

      sidebarMount.innerHTML = `
        <div class="brand-mark"><span class="dot"></span> RESOLVIX AI</div>
        <div class="nav-group">
          <div class="nav-label">Workspace</div>
          ${links}
        </div>
        <div class="sidebar-foot">
          <div class="user-chip">
            <div class="avatar">${Store.initials(user.name)}</div>
            <div>
              <div class="name">${user.name}</div>
              <div class="role">${user.email}</div>
            </div>
          </div>
          <a href="#" class="logout-link" id="logoutLink">Sign out</a>
        </div>`;

      document.getElementById('logoutLink').addEventListener('click', (e) => {
        e.preventDefault();
        Store.logout();
      });
    }

    const toggle = document.getElementById('menuToggle');
    const sidebar = document.querySelector('.sidebar');
    if (toggle && sidebar) {
      toggle.addEventListener('click', () => sidebar.classList.toggle('open'));
    }
  },

  toast(message) {
    let el = document.getElementById('shellToast');
    if (!el) {
      el = document.createElement('div');
      el.id = 'shellToast';
      el.className = 'toast';
      document.body.appendChild(el);
    }
    el.textContent = message;
    el.classList.add('show');
    clearTimeout(el._t);
    el._t = setTimeout(() => el.classList.remove('show'), 2600);
  }
};
