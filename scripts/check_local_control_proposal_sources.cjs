// Read-only: run the shipped proposal helper against actual saved PDF cells.
const fs=require('fs'),path=require('path'),vm=require('vm'),root=path.resolve(__dirname,'..');
const ts=require(path.join(root,'frontend_v2/node_modules/typescript'));
const compiled=ts.transpileModule(fs.readFileSync(path.join(root,'frontend_v2/src/features/financial/lib/statement-control-proposals.ts'),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText;
const context={exports:{}};vm.runInNewContext(compiled,context);
(async()=>{
 const login=await fetch('http://127.0.0.1:58002/api/auth/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({username:'loupe-local@example.com',password:'Loupe-local-test-2026'})});if(!login.ok)throw Error('Local login failed');
 const {access_token}=await login.json();
 const response=await fetch('http://127.0.0.1:58002/api/financial/candidate-sources/f256eda2-7ac7-46e9-855b-01a0ed0d7785/pages/1?case_id=e8ecc646-7b29-49d6-b64d-7086a9a14ad4&table_index=0',{headers:{Authorization:`Bearer ${access_token}`}});if(!response.ok)throw Error('Source read failed');const source=await response.json();
 const reports=[];
 for(const [role,expected] of [['opening balance','$6,700.18'],['closing balance','= $6,637.96']]){
  const candidates=context.exports.proposeStatementControls(source.rows,role);
  if(!candidates.some(p=>p.values.some(v=>v.expected_text===expected)))throw Error('Known control missing: '+role);
  if(role==='closing balance'&&candidates.some(p=>p.values.some(v=>v.expected_text==='$0.00')))throw Error('Unrelated other credits suggested as balance');
  for(const p of candidates)for(const value of p.values)if(!source.rows.find(r=>r.row_index===p.row)?.cells.some(c=>c===value))throw Error('Source reference was changed');
  reports.push({role,labelled_rows:candidates.length,value_choices:candidates.reduce((n,p)=>n+p.values.length,0),known_control_found:true});
 }
 if(context.exports.proposeStatementControls(source.rows,'total money out').length)throw Error('Summary subtotals mistaken for whole total');
 const report={case_id:source.case_id,page:1,controls:reports,subtotals_not_promoted:true,financial_writes:0};fs.writeFileSync(path.join(root,'data/local-runtime/control-proposal-source-check.json'),JSON.stringify(report,null,2));console.log(JSON.stringify(report));
})().catch(e=>{console.error(e);process.exitCode=1});
