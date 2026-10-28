import {chromium} from 'playwright';
import fs from 'node:fs';
if(process.env.GITHUB_ACTIONS!=='true')throw new Error('Disposable runner only');
const r=JSON.parse(fs.readFileSync(process.env.FOUNDATION_BUSINESS_REPORT)).records;
const report={status:'running',checks:[],scope:'Real browser Guardian REST/RPC/files and native login; no custom UI'};
const browser=await chromium.launch({headless:true});
try {
 const page=await browser.newPage();
 await page.goto('http://foundation.localhost:8080/login');
 await page.locator('#login_email').fill('validation-guardian@example.test');
 await page.locator('#login_password').fill(process.env.FOUNDATION_TEST_PASSWORD);
 await Promise.all([page.waitForURL(url=>url.pathname!=='/login'),page.locator('.for-login .form-login .btn-login[type=submit]').click()]);
 const paths=[['own-rest','/api/resource/Student/'+encodeURIComponent(r.students[0]),200],['other-rest','/api/resource/Student/'+encodeURIComponent(r.students[1]),403],['own-rpc','/api/method/frappe.client.get?doctype=Student&name='+encodeURIComponent(r.students[0]),200],['other-rpc','/api/method/frappe.client.get?doctype=Student&name='+encodeURIComponent(r.students[1]),403],['own-file',r.private_file_url,200],['other-file',r.guardian_other_file_url,403]];
 for(const [name,path,expected]of paths){
  const status=await page.evaluate(async path=>(await fetch(path,{credentials:'same-origin'})).status,path);
  report.checks.push({name,status:status===expected?'pass':'fail',http_status:status,expected});
 }
 report.status=report.checks.every(c=>c.status==='pass')?'pass':'fail';
}catch(e){report.status='fail';report.failure=String(e.message).slice(0,200);}
finally{await browser.close();fs.writeFileSync(process.env.FOUNDATION_GUARDIAN_BROWSER_REPORT,JSON.stringify(report,null,2));}
if(report.status!=='pass')process.exitCode=1;
