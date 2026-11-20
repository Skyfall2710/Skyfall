/**
 * Skyfall web localization helpers.
 *
 * The server injects window.__LANG__ and window.__WEB_I18N__ into the page.
 * Static HTML is localized server-side with Jinja's wt(); this file serves
 * dynamic JavaScript messages.
 */
(function () {
  'use strict';

  const lang = String(window.__LANG__ || 'ru').toLowerCase();
  const map = (window.__WEB_I18N__ && typeof window.__WEB_I18N__ === 'object')
    ? window.__WEB_I18N__
    : {};

  function tr(text, fallback) {
    if (text == null) return text;
    if (lang !== 'en') return text;
    if (Object.prototype.hasOwnProperty.call(map, text)) return map[text];
    return fallback !== undefined ? fallback : text;
  }

  function tf(template, vars) {
    let text = tr(template);
    if (!vars) return text;
    for (const key of Object.keys(vars)) {
      text = text.split('{' + key + '}').join(String(vars[key]));
    }
    return text;
  }

  window.__SKYFALL_LANG__ = lang;
  window.tr = tr;
  window.tf = tf;
})();
