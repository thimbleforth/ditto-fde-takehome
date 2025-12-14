const output = document.getElementById('output');
const loading = document.getElementById('loading');
const errorMessage = document.getElementById('errorMessage');
const modal = document.getElementById('modal');
const modalTitle = document.getElementById('modalTitle');
const saveBtn = document.getElementById('saveBtn');
let editId = null;

function showLoading(msg='Loading...'){
  loading.classList.add('active');
  document.getElementById('loadingText').textContent = msg;
}
function hideLoading(){ loading.classList.remove('active'); }
function showError(msg){ errorMessage.textContent = msg; errorMessage.classList.add('active'); hideLoading(); }
function hideError(){ errorMessage.classList.remove('active'); }

function renderReports(reports){
  if(!reports || reports.length===0){ output.innerHTML = '<div style="padding:2em;text-align:center;color:#999">No reports found.</div>'; return; }
  let html = `<div class="table-container"><table><thead><tr><th>ID</th><th>Report ID</th><th>Title</th><th>Content</th><th>Classification</th><th>Updated At</th><th>Updated By</th><th>Sync Status</th><th>Actions</th></tr></thead><tbody>`;
  reports.forEach(r => {
    const synced = r.is_synchronized === 1;
    const pending = r.is_synchronized === 0 && (!r.retry_count || r.retry_count===0);
    const failed = r.is_synchronized === 0 && (r.retry_count && r.retry_count>0);
    const status = synced ? `<span class="status-badge status-synced">Synchronized</span>` : pending ? `<span class="status-badge status-pending">Pending</span>` : `<span class="status-badge status-failed">Failed</span>`;
    const deletedClass = r.is_deleted===1 ? 'deleted' : '';
    html += `<tr class="${deletedClass}"><td>${escapeHtml(r.id)}</td><td>${escapeHtml(r.report_id)}</td><td>${escapeHtml(r.title)}</td><td><div style="max-width:260px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${escapeHtml(r.content)}</div></td><td>${escapeHtml(r.classification)}</td><td>${escapeHtml(r.updated_at)}</td><td>${escapeHtml(r.updated_by)}</td><td>${status}</td><td class="row-actions"><button onclick="editRecord(${r.id})">Edit</button><button onclick="deleteRecord(${r.id})">Delete</button></td></tr>`;
  });
  html += `</tbody></table></div>`;
  output.innerHTML = html;
}

function getReports(){ showLoading('Fetching reports...'); hideError(); fetch('/api/reports?include_deleted=true').then(r=>{ if(!r.ok) throw new Error(r.statusText); return r.json() }).then(data=>{ hideLoading(); renderReports(data)}).catch(e=> showError('Failed to fetch reports: '+e.message)); }

function getLatestReports(){ showLoading('Fetching latest reports...'); hideError(); fetch('/api/reports/latest').then(r=>{ if(!r.ok) throw new Error(r.statusText); return r.json() }).then(data=>{ hideLoading(); renderReports(data)}).catch(e=> showError('Failed to fetch latest: '+e.message)); }

function openCreateModal(){ editId = null; modalTitle.textContent = 'Create Report'; modal.classList.add('active'); document.getElementById('report_id').value=''; document.getElementById('title').value=''; document.getElementById('content').value=''; document.getElementById('classification').value='CUI'; document.getElementById('updated_by').value='web'; }
function closeModal(){ modal.classList.remove('active'); document.getElementById('report_id').disabled = false; }

function escapeHtml(str){ if(str===null||str===undefined) return ''; return String(str).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;').replace(/'/g,'&#039;'); }

saveBtn.addEventListener('click', ()=>{
  const payload = {
    report_id: document.getElementById('report_id').value.trim(),
    title: document.getElementById('title').value.trim(),
    content: document.getElementById('content').value.trim(),
    classification: document.getElementById('classification').value,
    updated_by: document.getElementById('updated_by').value.trim() || 'web'
  };
  // client-side validation
  const idRe = /^[A-Za-z0-9\-]+$/;
  if(!idRe.test(payload.report_id)){ showError('Invalid report_id format'); return }
  if(!payload.title || payload.title.length>255){ showError('Title required (max 255 chars)'); return }
  if(!payload.content || payload.content.length>2000){ showError('Content required (max 2000 chars)'); return }
  if(!['CUI','IL4','IL5'].includes(payload.classification)){ showError('Invalid classification'); return }

  showLoading('Saving...'); hideError();
  if(editId){
    fetch('/api/reports/'+editId, { method: 'PUT', headers: {'Content-Type':'application/json'}, body: JSON.stringify(payload)}).then(r=>{ if(!r.ok) return r.json().then(j=>{throw new Error(j.details||j.error||r.statusText)}) ; return r.json() }).then(()=>{ hideLoading(); closeModal(); getReports() }).catch(e=> showError('Failed to update report: '+e.message));
  } else {
    fetch('/api/reports', { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify(payload)}).then(r=>{ if(!r.ok) return r.json().then(j=>{throw new Error(j.details||j.error||r.statusText)}) ; return r.json() }).then(()=>{ hideLoading(); closeModal(); getReports() }).catch(e=> showError('Failed to create report: '+e.message));
  }
});

function editRecord(id){ showLoading('Loading record...'); hideError(); fetch('/api/reports?include_deleted=true').then(r=> r.json()).then(data=>{ const rec = data.find(x=> x.id===id); if(!rec){ hideLoading(); showError('Record not found'); return } document.getElementById('report_id').value = rec.report_id; document.getElementById('report_id').disabled = true; document.getElementById('title').value = rec.title; document.getElementById('content').value = rec.content; document.getElementById('classification').value = rec.classification; document.getElementById('updated_by').value = rec.updated_by; editId = id; modalTitle.textContent = 'Edit Report'; modal.classList.add('active'); hideLoading() }).catch(e=> showError('Failed to load record: '+e.message)); }

function deleteRecord(id){ if(!confirm('Are you sure you want to delete this report?')) return; showLoading('Deleting...'); hideError(); fetch('/api/reports/'+id, { method: 'DELETE', headers:{'Content-Type':'application/json'}, body: JSON.stringify({updated_by: 'web'}) }).then(r=>{ if(!r.ok) return r.json().then(j=>{throw new Error(j.details||j.error||r.statusText)}) ; return r.json() }).then(()=>{ hideLoading(); getReports() }).catch(e=> showError('Failed to delete: '+e.message)); }

function syncToCloud(){ showLoading('Syncing to cloud...'); hideError(); fetch('/api/sync', { method: 'POST' }).then(r=>{ if(!r.ok) return r.json().then(j=>{throw new Error(j.details||j.error||r.statusText)}) ; return r.json() }).then(summary=>{ hideLoading(); alert(`Sync complete: ${summary.successful||0} successful, ${summary.failed||0} failed`); getReports() }).catch(e=> showError('Sync failed: '+e.message)); }

// initial load
getReports();