// Applies the saved or system theme before first paint (no flash). External file: the CSP forbids inline scripts.
try {
  var t = localStorage.getItem('clarity.theme')
  if (t === 'dark' || (!t && matchMedia('(prefers-color-scheme: dark)').matches)) document.documentElement.classList.add('dark')
} catch (e) { /* storage blocked: light theme */ }
