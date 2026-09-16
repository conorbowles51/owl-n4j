// Publish the checked synthetic PDFs, testing instructions and synthetic screenshots.
const fs = require('node:fs');
const path = require('node:path');
const {pathToFileURL} = require('node:url');
const root = path.resolve(__dirname, '..');
const modules = path.join(root, 'frontend_v2/node_modules');
const out = path.join(root, 'frontend_v2/public/docs/financial-testing');
const source = fs.readFileSync(path.join(root, 'docs/user-guide/financial-team-checklist.md'), 'utf8');
if (source.includes('\u2014')) throw Error('Use plain punctuation in the team checklist.');
const slug = value => String(value).toLowerCase().replace(/[^a-z0-9\s-]/g, '').trim().replace(/\s+/g, '-');
(async () => {
  const React = require(path.join(modules, 'react'));
  const {renderToStaticMarkup} = require(path.join(modules, 'react-dom/server'));
  const {default: Markdown} = await import(pathToFileURL(require.resolve('react-markdown', {paths:[modules]})));
  const {default: gfm} = await import(pathToFileURL(require.resolve('remark-gfm', {paths:[modules]})));
  const {zipSync, strToU8} = require(path.join(modules, 'fflate'));
  const renderBody = markdown => renderToStaticMarkup(React.createElement(Markdown, {remarkPlugins:[gfm], components: {
    h2: ({children}) => React.createElement('h2', {id:slug(children)}, children),
    table: ({children}) => React.createElement('div', {className:'table-scroll'}, React.createElement('table', null, children)),
  }, children:markdown}));
  const body = renderBody(source);
  const html = `<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Loupe financial testing guide</title><style>body{font:17px/1.65 system-ui,sans-serif;color:#20252b;background:#f4f5f7;margin:0}main{max-width:960px;margin:24px auto;background:white;padding:32px}h1,h2,h3{line-height:1.3}h2{margin-top:2.2em;border-top:1px solid #ddd;padding-top:1em}a{color:#a71330;overflow-wrap:anywhere}li{margin:.5em 0}img{max-width:100%;height:auto;border:1px solid #ccc;border-radius:6px}.table-scroll{overflow-x:auto}table{border-collapse:collapse;width:100%;font-size:.9em}th,td{padding:9px;border:1px solid #ccc;text-align:left;vertical-align:top}th{background:#f5f5f5}@media(max-width:640px){main{padding:18px;margin:0}th,td{min-width:110px}}@media print{body{background:white;font-size:10pt}main{margin:0;padding:0}.table-scroll{overflow:visible}h2,h3{break-after:avoid}tr,img{break-inside:avoid}}</style><main>${body}</main></html>`;
  fs.mkdirSync(out, {recursive:true});
  const checking = fs.readFileSync(path.join(out,'checking.pdf'));
  const savings = fs.readFileSync(path.join(out,'savings.pdf'));
  const images = {};
  for (const match of source.matchAll(/!\[[^\]]*\]\((images\/[^)]+)\)/g)) {
    const name = match[1];
    if (!/^images\/[a-z0-9-]+\.png$/.test(name)) throw Error('Unexpected screenshot path: '+name);
    images[name] = fs.readFileSync(path.join(root,'docs/user-guide/testing-images',path.basename(name)));
    fs.mkdirSync(path.join(out,'images'),{recursive:true});
    fs.writeFileSync(path.join(out,name),images[name]);
  }
  fs.writeFileSync(path.join(out,'index.html'), html);
  fs.writeFileSync(path.join(out,'financial-team-checklist.md'), source);
  // The extracted guide must not link to a ZIP that is outside its own contents.
  const offlineMarkdown = source.replace('Alternatively, [download the test pack](financial-test-pack.zip) and extract its files first.', 'Both PDFs and all three guide images are already included in this extracted test pack.');
  const offlineHtml = html.replace(body, renderBody(offlineMarkdown));
  fs.writeFileSync(path.join(out,'financial-test-pack.zip'), zipSync({'checking.pdf':checking,'savings.pdf':savings,'checklist.html':strToU8(offlineHtml),'checklist.md':strToU8(offlineMarkdown),...images}, {level:6}));
  console.log(JSON.stringify({words:source.split(/\s+/).length,images:Object.keys(images).length,html_bytes:Buffer.byteLength(html)}));
})().catch(error=>{console.error(error);process.exitCode=1});
