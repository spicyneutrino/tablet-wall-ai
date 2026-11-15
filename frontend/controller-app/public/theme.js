(() => {
  try {
    const theme = localStorage.getItem('tablet-wall-theme');
    if (theme === 'light' || theme === 'dark') {
      document.documentElement.dataset.theme = theme;
    }
  } catch { /* Storage can be unavailable in private browser contexts. */ }
})();
