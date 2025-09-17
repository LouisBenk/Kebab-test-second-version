<script>
/* Lightweight i18n (DE/EN) with data-* attributes */
const I18N = (() => {
  let lang = 'de';
  let dict = {};
  const FALLBACKS = {}; // optional per-key fallbacks

  function get(obj, path) {
    return path.split('.').reduce((o,k)=> (o&&o[k]!=null)?o[k]:undefined, obj);
  }
  function t(key, fb) { return get(dict, key) ?? FALLBACKS[key] ?? fb ?? key; }

  function apply(root=document) {
    // Text nodes
    root.querySelectorAll('[data-i18n]').forEach(el => {
      el.textContent = t(el.dataset.i18n, el.textContent.trim());
    });
    // Attributes
    root.querySelectorAll('[data-i18n-title]').forEach(el => el.title = t(el.dataset.i18nTitle, el.title));
    root.querySelectorAll('[data-i18n-placeholder]').forEach(el => el.placeholder = t(el.dataset.i18nPlaceholder, el.placeholder));
    root.querySelectorAll('[data-i18n-aria-label]').forEach(el => el.setAttribute('aria-label', t(el.dataset.i18nAriaLabel, el.getAttribute('aria-label')||'')));

    document.documentElement.lang = lang;
    // Highlight active language buttons
    document.querySelectorAll('[data-lang]').forEach(btn => {
      const active = btn.dataset.lang === lang;
     btn.classList.toggle('is-active', active);

      btn.setAttribute('aria-pressed', active ? 'true' : 'false');
    });
  }

  async function set(newLang) {
    lang = newLang;
    localStorage.setItem('lang', lang);
    try {
    dict = await fetch(`/i18n/${lang}.json`, { cache: 'no-store' }).then(r => r.json());

    } catch {
      dict = {};
    }
    apply();
  }

  function init() {
    const saved = localStorage.getItem('lang');
    const browser = (navigator.language||'').slice(0,2);
    const start = saved || (['de','en'].includes(browser) ? browser : 'de');
    set(start);
    document.addEventListener('click', (e) => {
      const btn = e.target.closest('[data-lang]');
      if (btn) set(btn.dataset.lang);
    });
  }
  return { init, set, t };
})();
document.addEventListener('DOMContentLoaded', I18N.init);
</script>
