const API = '/api';
let token = null;
let role = null;

function navInit(){
  document.getElementById('nav-login').addEventListener('click', e=>{ e.preventDefault(); showLogin();});
  document.getElementById('nav-dashboard').addEventListener('click', e=>{ e.preventDefault(); showDashboard();});
  document.getElementById('nav-create').addEventListener('click', e=>{ e.preventDefault(); showCreate();});
  document.getElementById('nav-admin').addEventListener('click', e=>{ e.preventDefault(); showAdmin();});
}

function showMessage(msg){
  const main = document.getElementById('app');
  const d = document.createElement('div'); d.className='toast'; d.textContent = msg;
  main.prepend(d);
  setTimeout(()=>d.remove(), 4000);
}

function showLogin(){
  const main = document.getElementById('app'); main.innerHTML = '';
  const f = document.createElement('form');
  f.innerHTML = '<h2>Login</h2><input name="username" placeholder="usuario"><input name="password" type="password" placeholder="contraseña"><button>Entrar</button>';
  f.addEventListener('submit', async (ev)=>{
    ev.preventDefault();
    const fd = new FormData(f);
    const body = { username: fd.get('username'), password: fd.get('password') };
    try {
      const res = await fetch(API+'/auth/login', { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(body)});
      if(!res.ok) { showMessage('Login fallido'); console.error(await res.text()); return; }
      const j = await res.json(); token = j.access_token; role=j.role;
      showMessage('Login OK, role='+role);
      showDashboard();
    } catch(e){ console.error(e); showMessage('Error de red'); }
  });
  main.appendChild(f);
}

async function showDashboard(){
  const main = document.getElementById('app'); main.innerHTML = '<h2>Dashboard</h2>';
  try {
    const res = await fetch(API+'/courts');
    const courts = await res.json();
    const ul = document.createElement('div');
    ul.innerHTML = '<h3>Canchas</h3>';
    courts.forEach(c=> {
      const div = document.createElement('div');
      div.textContent = c.name + ' - ' + (c.location || '') + ' - $' + c.price;
      ul.appendChild(div);
    });
    main.appendChild(ul);
  } catch(e){ console.error(e); showMessage('No se pueden cargar canchas'); }
}

function showCreate(){
  const main = document.getElementById('app'); main.innerHTML = '<h2>Crear Reserva</h2>';
  const f = document.createElement('form');
  f.innerHTML = '<input name="court_id" placeholder="court id"><input name="start_ts" placeholder="YYYY-MM-DDTHH:MM:SS"><input name="end_ts" placeholder="YYYY-MM-DDTHH:MM:SS"><button>Reservar</button>';
  f.addEventListener('submit', async e=>{
    e.preventDefault();
    if(!token) { showMessage('Debe loguearse'); return; }
    const fd = new FormData(f); const body = { court_id: Number(fd.get('court_id')), start_ts: fd.get('start_ts'), end_ts: fd.get('end_ts')};
    try {
      const res = await fetch(API+'/reservations', { method:'POST', headers:{'Content-Type':'application/json','Authorization':'Bearer '+token}, body:JSON.stringify(body)});
      if(res.status===201){ const j=await res.json(); showMessage('Reserva creada id='+j.id); console.log('created', j); }
      else { const t = await res.text(); showMessage('Error: '+res.status); console.error(t); }
    } catch(e){ console.error(e); showMessage('Error de red'); }
  });
  main.appendChild(f);
}

async function showAdmin(){
  const main = document.getElementById('app'); main.innerHTML = '<h2>Admin - Bitácora (solo admin)</h2>';
  if(!token) { showMessage('Debe loguearse como admin'); return; }
  try {
    const res = await fetch(API+'/audit_log', { headers:{ 'Authorization':'Bearer '+token } });
    if(!res.ok){ showMessage('Acceso denegado o no admin'); return; }
    const rows = await res.json();
    rows.forEach(r=> {
      const d = document.createElement('div'); d.textContent = `[${r.created_at}] ${r.actor || 'system'} - ${r.action} - ${r.details}`; main.appendChild(d);
    });
  } catch(e){ console.error(e); showMessage('Error al obtener bitácora'); }
}

window.addEventListener('load', ()=>{ navInit(); showDashboard(); });
