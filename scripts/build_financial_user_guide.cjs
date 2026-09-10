// Build a portable user guide from the checked Markdown and local screenshots.
// Uses existing frontend dependencies. No network requests or case writes.
const fs = require('fs');
const path = require('path');
const { pathToFileURL } = require('url');
const root = path.resolve(__dirname, '..');
const modules = path.join(root, 'frontend_v2/node_modules');
const dir = path.join(root, 'docs/user-guide');
const React = require(path.join(modules, 'react'));
const { renderToStaticMarkup } = require(path.join(modules, 'react-dom/server'));
const slug = value => String(value).toLowerCase().replace(/[^a-z0-9\s-]/g, '').trim().replace(/\s+/g, '-');
(async () => {
  const { default: Markdown } = await import(pathToFileURL(require.resolve('react-markdown', {paths: [modules]})));
  const { default: gfm } = await import(pathToFileURL(require.resolve('remark-gfm', {paths: [modules]})));
  const source = fs.readFileSync(path.join(dir, 'financial-user-guide.md'), 'utf8');
  if (source.includes('\u2014')) throw Error('The guide must not contain em dashes.');
  const body = renderToStaticMarkup(React.createElement(Markdown, {
    remarkPlugins: [gfm],
    components: {
      h2: ({children}) => React.createElement('h2', {id: slug(children)}, children),
      img: ({src, alt}) => {
        if (!src.startsWith('images/')) throw Error('Only local guide screenshots are allowed.');
        const file = path.resolve(dir, src);
        if (!file.startsWith(path.join(dir, 'images') + path.sep)) throw Error('Invalid image path.');
        return React.createElement('img', {src: 'data:image/png;base64,' + fs.readFileSync(file).toString('base64'), alt, loading: 'lazy'});
      },
      table: ({children}) => React.createElement('div', {className: 'table-scroll'}, React.createElement('table', null, children)),
    },
    children: source,
  }));
  const html = `<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Loupe financial user guide</title><style>
:root{color-scheme:light;font-family:Arial,Helvetica,sans-serif;color:#19252e;background:#f1f3f5;font-size:17px;line-height:1.65}*{box-sizing:border-box}body{margin:0}header{background:#18252e;color:white;padding:14px 5vw;position:sticky;top:0;z-index:1;display:flex;gap:20px;justify-content:space-between}header a{color:white}main{max-width:1060px;margin:32px auto;background:white;padding:50px 64px;box-shadow:0 2px 15px #0001}h1{font-size:2.5rem;line-height:1.15;letter-spacing:-.04em}h2{font-size:1.7rem;line-height:1.3;margin-top:3.5rem;padding-top:1rem;border-top:3px solid #8b3145;scroll-margin-top:85px}h3{font-size:1.18rem;margin-top:2rem;line-height:1.4}a{color:#87314a;text-underline-offset:3px}li{margin:.45rem 0}li::marker{font-weight:bold;color:#87314a}strong{font-weight:700}img{display:block;max-width:100%;height:auto;margin:24px 0 10px;border:1px solid #ccd2d7;border-radius:6px}p:has(>em:only-child){font-size:.9rem;color:#4d5c69;margin-top:8px}.table-scroll{overflow-x:auto;margin:20px 0}table{border-collapse:collapse;width:100%;font-size:.94rem}th,td{border:1px solid #d7dce1;text-align:left;padding:12px 14px;vertical-align:top}th{background:#e9eef2;color:#15222d}tr:nth-child(even){background:#f8fafb}code{font-size:.9em;background:#eef1f4;padding:2px 5px;border-radius:3px}input[type=checkbox]{margin-right:8px}footer{max-width:1060px;margin:20px auto 40px;padding:0 25px;color:#57636d} @media(max-width:650px){:root{font-size:16px}main{margin:0;padding:24px 20px}h1{font-size:2rem}header{position:static;flex-wrap:wrap}h2{scroll-margin-top:16px}th,td{min-width:145px;padding:9px}} @media print{@page{size:A4;margin:18mm}body{background:white;font-size:10pt}header,footer{display:none}main{padding:0;margin:0;box-shadow:none;max-width:none}h2{break-before:page;scroll-margin:0}h2,h3{break-after:avoid}img,tr{break-inside:avoid}img{max-height:180mm;object-fit:contain}a{color:inherit}.table-scroll{overflow:visible}th,td{padding:7px}p,li{orphans:3;widows:3}}
</style></head><body><header><span>Loupe financial user guide</span><a href="#contents">Contents</a></header><main>${body}</main><footer>10 September 2026. Screenshots show synthetic development data. Keep the original exported case records separately from this guide.</footer></body></html>`;
  fs.writeFileSync(path.join(dir, 'financial-user-guide.html'), html);
  const publicDir = path.join(root, 'frontend_v2/public/docs/financial-guide');
  fs.mkdirSync(publicDir, {recursive:true});
  fs.writeFileSync(path.join(publicDir, 'financial-user-guide.md'), source);
  fs.cpSync(path.join(dir, 'images'), path.join(publicDir, 'images'), {recursive:true});
  console.log(JSON.stringify({words:source.split(/\s+/).length,images:(source.match(/!\[/g)||[]).length,bytes:Buffer.byteLength(html)}));
})().catch(error => {console.error(error);process.exitCode=1});
