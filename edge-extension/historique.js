async function captureWafaHistory(tabId, expectedAccount) {
 const viewUrl=WAFA+'/portefeuille/historique';
 await chrome.tabs.update(tabId,{url:viewUrl});
 async function read(action, previous) {
  const result=await chrome.scripting.executeScript({target:{tabId},args:[action,previous],func:(action,previous)=>{
   if(location.origin!=='https://clients.wafabourse.com'||location.pathname!=='/portefeuille/historique')return null;
   const clean=value=>String(value||'').replace(/\s+/g,' ').trim();
   const norm=value=>clean(value).normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLowerCase();
   const buttons=[...document.querySelectorAll('button')];
   const button=label=>buttons.find(b=>norm(b.innerText)===label);
   const account=buttons.find(b=>/Portefeuille\s*\(PEA\)/i.test(b.innerText))?.innerText.replace(/\s+/g,'');
   if(!account)return null;
   const table=[...document.querySelectorAll('table')].find(t=>norm(t.tHead?.innerText||t.querySelector('tr')?.innerText).includes('montant net'));
   const next=button('suivant');
   const back=button('precedent');
   if(!table||!next||!back)return null;
   const header=[...table.querySelectorAll('tr')].find(row=>row.querySelector('th'));
   const labels=[...header.children].map(c=>norm(c.innerText));
   const cols=[/^date$/, /^operation$/, /^valeur$/, /^(qte|quantite)$/, /^cours$/, /^montant net$/, /^commissions?$/, /^tva$/]
    .map(pattern=>labels.findIndex(label=>pattern.test(label)));
   if(cols.some(index=>index<0))throw Error('Colonnes Historique non reconnues.');
   const disabled=element=>element.disabled||element.getAttribute('aria-disabled')==='true'||element.classList.contains('disabled');
   const rows=[];
   const indices=[];
   for(const row of table.querySelectorAll('tbody tr')){
    const cells=[...row.querySelectorAll('td')];
    if(!cells.length)continue;
    if(cells.length<=Math.max(...cols))return null;
    const [date,rawType,name,qty,price,net,fees,tax]=cols.map(i=>clean(cells[i].innerText));
    const index=clean(cells[0].innerText);
    if(!/^\d+$/.test(index)||!/^\d{2}\/\d{2}\/\d{4}$/.test(date))return null;
    const normalized=norm(rawType);
    const type=normalized.startsWith('souscrip')?'SOUSCRIPTION':normalized==='credit'?'Credit':normalized==='debit'?'Debit':rawType;
    rows.push([date+' '+type,name,qty,price,net,fees||'0','0','0',tax||'0'].join('  '));
    indices.push(Number(index));
   }
   if(!rows.length)return null;
   const signature=JSON.stringify([indices,rows]);
   if(action==='next'&&signature===previous&&!disabled(next)){next.click();return {clicked:true};}
   return {account,rows,indices,signature,first:disabled(back),last:disabled(next)};
  }});
  return result[0]?.result;
 }
 async function ready(previous) {
  for(let attempt=0;attempt<30;attempt++){
   const tab=await chrome.tabs.get(tabId);
   if(tab.url===viewUrl&&tab.status==='complete'){
    const page=await read();
    if(page&&page.signature!==previous)return page;
   }
   await new Promise(resolve=>setTimeout(resolve,500));
  }
  throw Error('Historique Wafa incomplet ou page suivante non chargée.');
 }
 let page=await ready();
 if(!page.first||page.indices[0]!==1)throw Error('Historique : la première page n’a pas été détectée.');
 const history=[];
 for(let count=0;count<100;count++){
  if(page.account!==expectedAccount)throw Error('Le compte a changé dans Historique.');
  for(let i=0;i<page.rows.length;i++){
   if(page.indices[i]!==history.length+1)throw Error('Pagination Historique incohérente.');
   history.push(page.rows[i]);
  }
  if(page.last){
   const result=history.join('\n');
   if(result.length>220000)throw Error('Historique trop volumineux pour cette lecture.');
   return result;
  }
  const transition=await read('next',page.signature);
  if(!transition?.clicked)throw Error('Impossible de passer à la page suivante.');
  page=await ready(page.signature);
 }
 throw Error('Historique trop volumineux : la lecture a été interrompue.');
}
