// Single unified footer — GeoCroissant + Mintlify powered-by in one block
(function() {
  function addCopyright() {
    const footer = document.querySelector('footer');
    if (!footer || document.getElementById('geocr-copyright')) return;
    const copyright = document.createElement('div');
    copyright.id = 'geocr-copyright';
    copyright.innerHTML = 'Copyright © GeoCroissant Contributors · GeoCroissant is the geospatial extension of <a href="https://mlcommons.org/croissant/">MLCommons Croissant</a>';
    // Insert right after Mintlify's "Powered by" so both sit in one centered block
    const poweredBy = Array.from(footer.querySelectorAll('*')).find(el => /Powered by/i.test(el.textContent || ''));
    if (poweredBy && poweredBy.parentElement === footer) {
      poweredBy.insertAdjacentElement('afterend', copyright);
    } else if (poweredBy) {
      poweredBy.closest('div')?.insertAdjacentElement('afterend', copyright);
    } else {
      footer.appendChild(copyright);
    }
  }

  // Run on initial load
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', addCopyright);
  } else {
    addCopyright();
  }

  // Handle SPA navigation
  const observer = new MutationObserver(addCopyright);
  observer.observe(document.body, { childList: true, subtree: true });
})();
