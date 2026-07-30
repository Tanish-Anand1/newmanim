
  // Environment & Supabase Setup
  const SUPABASE_URL = 'https://ykojwrclyhyyqburnbyh.supabase.co';
  const SUPABASE_ANON_KEY = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Inlrb2p3cmNseWh5eXFidXJuYnloIiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODQwNjU4NjgsImV4cCI6MjA5OTY0MTg2OH0.RpLfPVoGxPLkFDM05BatqbVNTs02Ci_hs8XOj6O1cMI';
  const RAILWAY_URL = 'https://vivacity-production.up.railway.app';
  
  const isLocal = location.hostname === 'localhost' || location.hostname === '127.0.0.1' || location.hostname === '' || location.hostname.startsWith('192.168.') || location.hostname.startsWith('10.');
  const localBackend = (location.hostname === '' || location.hostname === 'localhost' || location.hostname === '127.0.0.1') 
      ? 'http://localhost:8000' 
      : `http://${location.hostname}:8000`;
      
  const BASE_URL = window.__BACKEND_URL__ || (isLocal ? localBackend : RAILWAY_URL);

  const supabaseClient = window.supabase.createClient(SUPABASE_URL, SUPABASE_ANON_KEY);
  let sessionData = null;

  async function checkAuth() {
    // Local Vivacity uses the project backend directly; do not require the
    // reference site's hosted Supabase session during local development.
    sessionData = { access_token: '' };
  }
  checkAuth();

  // Listen for auth state changes
  supabaseClient.auth.onAuthStateChange((event, session) => {
    if (event === 'SIGNED_OUT') {
      window.location.href = 'signup.html';
    } else if (session) {
      sessionData = session;
    }
  });

  async function apiFetch(endpoint, options = {}) {
    if (!sessionData) {
      // Wait briefly for auth state if not loaded
      const { data } = await supabaseClient.auth.getSession();
      sessionData = data.session;
    }
    let backendUrl = getSetting('backendUrl', 'http://127.0.0.1:8000');
    if (backendUrl === 'RAILWAY_BACKEND_URL_PLACEHOLDER') backendUrl = BASE_URL;
    options.headers = {
      ...options.headers,
      'Authorization': `Bearer ${sessionData ? sessionData.access_token : ''}`
    };
    const res = await fetch(backendUrl + endpoint, options);
    if (res.status === 401) {
      await logout();
    }
    return res;
  }

  async function logout() {
    await supabaseClient.auth.signOut();
    window.location.href = 'signup.html';
  }

  const STEPS = ['scripting','audio','coding','rendering','stitching'];
  let pollInterval=null, currentFormat='portrait', currentLang='english', currentJobId=null, currentVideoUrl=null, currentManimCode=null, currentSessionId=null, currentRecallQuestion=null;
  const MODELS = ['claude-opus','claude-sonnet','claude-haiku'];
  let modelIdx=0;

  function getSetting(k,def){const s=JSON.parse(localStorage.getItem('viv_settings')||'{}');return s[k]!==undefined?s[k]:def;}
  function saveSetting(k,v){const s=JSON.parse(localStorage.getItem('viv_settings')||'{}');s[k]=v;localStorage.setItem('viv_settings',JSON.stringify(s));}
  
  async function loadSettings(){
    const s=JSON.parse(localStorage.getItem('viv_settings')||'{}');
    if(s.accent)applyAccentColor(s.accent,s.accentRgb||'0,195,255');
    if(s.projName){document.getElementById('proj-name').textContent=s.projName;document.getElementById('s-proj-name').value=s.projName;}
    
    // Also try to load settings from DB
    try {
      const res = await apiFetch('/settings');
      if (res.ok) {
        const dbSettings = await res.json();
        if (dbSettings.font) { setFont(dbSettings.font); } else if (s.font) { setFont(s.font); } else { setFont('geist'); }
      }
    } catch(e) {
      if(s.font){setFont(s.font);} else {setFont('geist');}
    }

    if(s.displayName)document.getElementById('s-display-name').value=s.displayName;
    if(s.nickname)document.getElementById('s-nickname').value=s.nickname;
    if(s.backendUrl){document.getElementById('s-backend-url').value=s.backendUrl;window.__BACKEND_URL__=s.backendUrl;}
    if(s.instructions)document.getElementById('s-instructions').value=s.instructions;
    if(s.format){currentFormat=s.format;setFmt(s.format,true);settingSetFmt(s.format,true);}
    if(s.lang){currentLang=s.lang;setLang(s.lang,true);settingSetLang(s.lang,true);}
    loadMemoryTags();loadHistory();loadFiles();
  }

  function setFmt(f,silent){currentFormat=f;['portrait','landscape'].forEach(v=>document.getElementById('fmt-'+v)?.classList.toggle('active',v===f));if(!silent)saveSetting('format',f);}
  function setLang(l,silent){currentLang=l;['english','hinglish'].forEach(v=>document.getElementById('lang-'+v)?.classList.toggle('active',v===l));document.getElementById('chat-input').placeholder=l==='hinglish'?'Animation describe karo...':'Describe your animation...';if(!silent)saveSetting('lang',l);}
  function settingSetFmt(f,silent){['portrait','landscape'].forEach(v=>document.getElementById('s-fmt-'+v)?.classList.toggle('active',v===f));if(!silent)setFmt(f);}
  function settingSetLang(l,silent){const m={english:'en',hinglish:'hi'};['en','hi'].forEach(v=>document.getElementById('s-lang-'+v)?.classList.toggle('active',m.english===v?l==='english':l==='hinglish'));if(!silent)setLang(l);}

  function setSidebarView(view){
    ['chat','history','files','templates'].forEach(v=>{document.getElementById('sb-'+v)?.classList.remove('active');document.getElementById('view-'+v)?.classList.remove('active');});
    document.getElementById('sb-'+view)?.classList.add('active');
    document.getElementById('view-'+view)?.classList.add('active');
    const titles={chat:'Vivacity AI',history:'History',files:'Files',templates:'Templates'};
    document.getElementById('panel-title').textContent=titles[view]||'Vivacity AI';
    if(view==='history')loadHistory();
    if(view==='files')loadFiles();
  }

  async function addToHistory(prompt,jobId,videoUrl){
    // DB sync is handled automatically on backend /generate
    // We just refresh local history view
    loadHistory();
  }

  async function loadHistory(){
    const c=document.getElementById('history-list'),e=document.getElementById('history-empty');
    if(!c)return;
    try {
      const res = await apiFetch('/sessions');
      if (!res.ok) throw new Error();
      const h = await res.json();
      
      if(h.length===0){if(e)e.style.display='flex';return;}
      if(e)e.style.display='none';
      c.querySelectorAll('.history-item').forEach(el=>el.remove());
      h.forEach(item=>{
        const el=document.createElement('div');el.className='history-item';
        el.innerHTML=`<div class="history-item-prompt">${escHtml(item.title)}</div><div class="history-item-meta">${new Date(item.created_at).toLocaleString()}</div><div class="history-item-status">✓ Complete</div>`;
        el.onclick=()=>{
          currentSessionId = item.id;
          setSidebarView('chat');
          loadSessionMessages(item.id);
        };
        c.appendChild(el);
      });
    } catch(err) {
      if(e)e.style.display='flex';
    }
  }

  async function loadSessionMessages(sessionId) {
    const res = await apiFetch(`/sessions/${sessionId}/messages`);
    if(res.ok) {
       const msgs = await res.json();
       document.getElementById('rp-msgs').innerHTML = '';
       msgs.forEach(m => {
         if (m.role === 'user') addUserMessage(m.content, true);
         else addAiMessage(m.content, null, null, true);
       });
    }
  }

  function loadVideoFromHistory(item){setSidebarView('chat');document.getElementById('viewer-filename').textContent='render_'+(item.jobId||'').slice(0,8)+'.mp4';const c=document.getElementById('main-video-container');c.style.display='block';c.style.aspectRatio=item.format==='portrait'?'9/16':'16/9';c.style.maxWidth=item.format==='portrait'?'360px':'100%';const v=document.getElementById('main-video');v.src=item.videoUrl;v.load();v.play().catch(()=>{});}
  function addToFiles(fname,url,fmt){const f=JSON.parse(localStorage.getItem('viv_files')||'[]');f.unshift({filename:fname,url,format:fmt,time:new Date().toISOString()});localStorage.setItem('viv_files',JSON.stringify(f));}
  function loadFiles(){
    const f=JSON.parse(localStorage.getItem('viv_files')||'[]');
    const c=document.getElementById('files-list'),e=document.getElementById('files-empty');
    if(!c)return;
    if(f.length===0){if(e)e.style.display='flex';return;}
    if(e)e.style.display='none';
    c.querySelectorAll('.file-item').forEach(el=>el.remove());
    f.forEach(fi=>{const el=document.createElement('div');el.className='file-item';el.innerHTML=`<div class="file-item-icon"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="13" height="13"><polygon points="23 7 16 12 23 17 23 7"/><rect x="1" y="5" width="15" height="14" rx="2"/></svg></div><div class="file-item-info"><div class="file-item-name">${escHtml(fi.filename)}</div><div class="file-item-meta">${new Date(fi.time).toLocaleDateString()} · ${fi.format||'landscape'}</div></div><div class="file-item-dl" onclick="event.stopPropagation();downloadFile('${fi.url}','${fi.filename}')"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg></div>`;el.onclick=()=>loadVideoFromHistory({videoUrl:fi.url,format:fi.format,jobId:fi.filename});c.appendChild(el);});
  }
  function downloadFile(url,name){const a=document.createElement('a');a.href=url;a.download=name;a.click();}
  function useTemplate(text){document.getElementById('chat-input').value=text;document.getElementById('chat-input').focus();setSidebarView('chat');closeMobilePanel();}
  function togglePlusMenu(e){e.stopPropagation();document.getElementById('model-picker')?.classList.remove('open');document.getElementById('plus-dropdown').classList.toggle('open');}
  function triggerFileUpload(){document.getElementById('plus-dropdown').classList.remove('open');document.getElementById('file-input').click();}
  function handleFileUpload(e){const f=e.target.files[0];if(!f)return;toast('📎 Attached: '+f.name);addUserMessage('[Attached: '+f.name+']');}
  function addToProject(){document.getElementById('plus-dropdown').classList.remove('open');toast('📁 Added to project');}
  function switchTab(el,tab){document.querySelectorAll('.vtab').forEach(t=>t.classList.remove('active'));el.classList.add('active');document.getElementById('tab-preview').style.display='none';document.getElementById('tab-code').classList.remove('visible');document.getElementById('tab-logs').classList.remove('visible');if(tab==='preview')document.getElementById('tab-preview').style.display='flex';else if(tab==='code'){document.getElementById('tab-code').classList.add('visible');document.getElementById('code-display').textContent=currentManimCode||'# No code yet — generate a video first.';}else document.getElementById('tab-logs').classList.add('visible');}
  // ─── Mode & Model ────────────────────────────────────────────────────────────
  let currentMode = 'viva'; // 'viva' | 'video'
  let chatHistory = []; // keep running context for Viva

  function toggleModelPicker(e) {
    e.stopPropagation();
    document.getElementById('plus-dropdown').classList.remove('open');
    document.getElementById('model-picker').classList.toggle('open');
  }
  document.addEventListener('click', () => {
    document.getElementById('plus-dropdown')?.classList.remove('open');
    document.getElementById('model-picker')?.classList.remove('open');
  });

  function selectMode(mode) {
    currentMode = mode;
    document.getElementById('model-picker').classList.remove('open');
    document.querySelectorAll('.model-option').forEach(o => o.classList.remove('active'));
    document.getElementById('mopt-' + mode)?.classList.add('active');
    const dot = document.getElementById('model-picker-trigger').querySelector('svg:first-child');
    if (mode === 'viva') {
      document.getElementById('input-model-label').textContent = 'Viva';
      dot.style.color = 'var(--accent)';
      document.getElementById('chat-input').placeholder = 'Ask Viva anything...';
    } else {
      document.getElementById('input-model-label').textContent = 'Video Render';
      dot.style.color = '#a855f7';
      document.getElementById('chat-input').placeholder = 'Describe your animation to render...';
    }
  }

  function insertVideoTrigger() {
    document.getElementById('plus-dropdown').classList.remove('open');
    const inp = document.getElementById('chat-input');
    inp.value = '/video ';
    inp.focus();
  }

  function isVideoIntent(text) {
    if (text.startsWith('/video')) return true;
    if (currentMode === 'video') return true;
    // Detect strong video generation intent
    const triggers = [
      /\bgenerate (a |an )?video\b/i,
      /\bmake (a |an )?video\b/i,
      /\bcreate (a |an )?(animation|video|visualization)\b/i,
      /\banimate\b/i,
      /\bvisuali[sz]e\b/i,
      /\brender( this| that)?\b/i,
    ];
    return triggers.some(r => r.test(text));
  }

  function sendMessage() {
    const inp = document.getElementById('chat-input');
    const text = inp.value.trim();
    if (!text) { toast('Enter a topic or question first.'); return; }
    if (pollInterval) { toast('⏳ Render in progress — wait for it to finish.'); return; }
    inp.value = '';
    // auto-resize
    inp.style.height = '38px';
    addUserMessage(text);
    chatHistory.push({ role: 'user', content: text });
    if (isVideoIntent(text)) {
      const cleanPrompt = text.replace(/^\/video\s*/i, '').trim() || text;
      startGeneration(cleanPrompt);
    } else {
      sendToViva();
    }
  }

  function handleChatKey(e) {
    if ((e.key === 'Enter' || e.keyCode === 13) && !e.shiftKey) { 
      e.preventDefault(); 
      sendMessage(); 
      return;
    }
    setTimeout(autoResizeChat, 0);
  }
  function autoResizeChat() {
    const el = document.getElementById('chat-input');
    el.style.height = '38px';
    el.style.height = Math.min(el.scrollHeight, 160) + 'px';
  }
  function triggerRender() { const t = document.getElementById('chat-input').value.trim(); if (t) sendMessage(); else toast('Type a prompt first.'); }

  // ─── Viva Streaming Chat ──────────────────────────────────────────────────────
  async function sendToViva() {
    const thinkEl = document.getElementById('thinking-msg');
    document.getElementById('think-label-text').textContent = 'Viva is thinking...';
    thinkEl.style.display = 'flex';
    scrollChat();
    const sendBtn = document.getElementById('send-btn');
    sendBtn.disabled = true;

    // Create streaming AI bubble
    const msgEl = document.createElement('div');
    msgEl.className = 'msg ai';
    msgEl.innerHTML = `<div class="msg-avatar" style="background:linear-gradient(135deg,#00c3ff22,#0055ff22);border-color:rgba(0,195,255,0.3);color:var(--accent);">V</div><div><div class="msg-bubble" id="viva-streaming-bubble"></div></div>`;

    try {
      const res = await apiFetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ messages: chatHistory.slice(-20) }) // last 20 messages for context
      });

      if (!res.ok) throw new Error('Status ' + res.status);

      thinkEl.style.display = 'none';
      document.getElementById('rp-msgs').appendChild(msgEl);
      scrollChat();

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      const bubble = document.getElementById('viva-streaming-bubble');
      let fullText = '';
      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop(); // Keep incomplete line in buffer
        
        for (const line of lines) {
          if (!line.trim() || !line.startsWith('data: ')) continue;
          const data = line.slice(6).trim();
          if (data === '[DONE]') break;
          let parsed;
          try { parsed = JSON.parse(data); } catch(_) { continue; }
          if (parsed.error) throw new Error(parsed.error);
          if (parsed.token) {
            fullText += parsed.token;
            bubble.innerHTML = markdownToHtml(fullText);
            scrollChat();
          }
        }
      }
      if (fullText) {
        bubble.removeAttribute('id');
        chatHistory.push({ role: 'assistant', content: fullText });
      } else {
        // Stream finished with no content — backend error
        msgEl.remove();
        throw new Error('Viva returned an empty response. Backend may be down.');
      }
    } catch (err) {
      thinkEl.style.display = 'none';
      addAiMessage('⚠️ ' + (err.message || 'Could not reach Viva. Check your backend.'), null, null);
    } finally {
      sendBtn.disabled = false;
    }
  }

  function markdownToHtml(md) {
    // Simple markdown: bold, inline code, code blocks, line breaks
    return md
      .replace(/```([\s\S]*?)```/g, '<pre style="background:var(--bg-3);padding:10px 12px;border-radius:8px;font-size:12px;overflow-x:auto;margin:8px 0;"><code>$1</code></pre>')
      .replace(/`([^`]+)`/g, '<code style="background:var(--bg-3);padding:1px 6px;border-radius:4px;font-size:12px;">$1</code>')
      .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
      .replace(/\*(.+?)\*/g, '<em>$1</em>')
      .replace(/^### (.+)$/gm, '<div style="font-size:12px;font-weight:700;margin:10px 0 4px;color:var(--t1);">$1</div>')
      .replace(/^## (.+)$/gm, '<div style="font-size:13px;font-weight:700;margin:10px 0 4px;color:var(--t1);">$1</div>')
      .replace(/^# (.+)$/gm, '<div style="font-size:14px;font-weight:700;margin:10px 0 4px;color:var(--t1);">$1</div>')
      .replace(/^- (.+)$/gm, '<div style="padding-left:14px;margin:2px 0;">• $1</div>')
      .replace(/\n/g, '<br>');
  }
  async function startGeneration(question){
    const thinkEl=document.getElementById('thinking-msg');document.getElementById('think-label-text').textContent='Connecting...';thinkEl.style.display='flex';scrollChat();
    const sendBtn=document.getElementById('send-btn');sendBtn.disabled=true;sendBtn.style.opacity='0.35';
    showProgressOverlay();document.getElementById('video-options').style.display='none';document.getElementById('log-display').textContent='';appendLog('$ vivacity generate --format '+currentFormat+' --lang '+currentLang);appendLog('  [Prompt] '+question);
    currentManimCode=null;currentVideoUrl=null;
    
    try {
      const res = await apiFetch('/api/generate',{
        method:'POST',
        headers:{'Content-Type':'application/json'},
        body:JSON.stringify({
          topic: question,
          audience: 'high school',
          duration_seconds: 60,
          orientation: currentFormat,
          scene_name: 'VivacityGeneratedScene',
          pipeline_profile: 'template',
          exam_context: document.getElementById('video-exam').value,
          student_signal: {
            self_rated_confidence: Number(document.getElementById('video-confidence').value),
            flagged_as_weak_topic: document.getElementById('video-weak-topic').checked,
            prior_attempt_count: 0,
            unconfirmed_prerequisites: Array.from(document.querySelectorAll('.video-prereq:checked')).map(el => el.value)
          },
          assumed_prerequisites: Array.from(document.querySelectorAll('.video-prereq:checked')).map(el => el.value)
        })
      });
      if(!res.ok){const err=await res.text();throw new Error('Server '+res.status+': '+err);}
      const{job_id}=await res.json();currentJobId=job_id;appendLog('  [Job] '+job_id);thinkEl.style.display='none';pollJob(job_id);}
    catch(err){thinkEl.style.display='none';sendBtn.disabled=false;sendBtn.style.opacity='1';showError(err.message);addAiMessage('❌ Cannot reach backend. Go to <strong>Settings → Backend</strong> to configure the URL.',null,null);}
  }
  function pollJob(job_id){if(pollInterval)clearInterval(pollInterval);pollInterval=setInterval(async()=>{try{const res=await apiFetch('/api/jobs/'+job_id);if(!res.ok)return;const job=await res.json();updateProgress(job);if(job.status==='complete'){clearInterval(pollInterval);pollInterval=null;onJobDone(job);}else if(job.status==='failed'){clearInterval(pollInterval);pollInterval=null;onJobError(job);}}catch(_){}},1500);}
  function updateProgress(job){const status=job.status||'';const progress=job.progress||({queued:3,generating_storyboard:12,generating_voiceover:28,generating_code:42,rendering:62,retrying:48,muxing:86,complete:100,failed:100}[status]||0);const message=job.progress_message||job.message||status;document.getElementById('prog-bar').style.width=progress+'%';document.getElementById('prog-pct').textContent=progress+'%';document.getElementById('prog-msg').textContent=message;const stageIndex={queued:0,generating_storyboard:0,generating_voiceover:1,generating_code:2,retrying:2,rendering:3,muxing:4,complete:5,failed:5}[status]??0;const activeStage=status==='muxing'?'stitching':status==='rendering'?'rendering':status==='generating_code'||status==='retrying'?'coding':status==='generating_voiceover'?'audio':'scripting';STEPS.forEach((step,index)=>{const el=document.getElementById('pstep-'+step);if(!el)return;el.className='prog-step';const icon=el.querySelector('.prog-step-icon');if(index<stageIndex||(status==='complete')){el.classList.add('done');if(icon)icon.textContent='✓';}else if(index===stageIndex&&status!=='failed'){el.classList.add('active');if(icon)icon.textContent='●';}});appendLog('  ['+status.toUpperCase()+'] '+message);}
  function onJobDone(job){const videoUrl=(job.output_video_url&&job.output_video_url.startsWith('http'))?job.output_video_url:('http://127.0.0.1:8000'+(job.output_video_url||''));currentVideoUrl=videoUrl;appendLog('  [Done] Video ready!');const fname='render_'+currentJobId.slice(0,8)+'.mp4';document.getElementById('viewer-filename').textContent=fname;document.getElementById('progress-overlay').classList.remove('visible');const c=document.getElementById('main-video-container');c.style.display='block';c.style.aspectRatio=currentFormat==='portrait'?'9/16':'16/9';c.style.maxWidth=currentFormat==='portrait'?'360px':'100%';const v=document.getElementById('main-video');v.src=videoUrl;v.load();v.play().catch(()=>{});const sendBtn=document.getElementById('send-btn');sendBtn.disabled=false;sendBtn.style.opacity='1';addToHistory(document.querySelector('#rp-msgs .msg.user:last-of-type .msg-bubble')?.textContent||'Render',currentJobId,videoUrl);addToFiles(fname,videoUrl,currentFormat);addAiMessage('✅ Done! <strong>'+fname+'</strong> is ready.',currentJobId,fname);showRecallQuestion(job);toast('🎬 Video ready!');}
  function showRecallQuestion(job){const q=job.recall_question;if(!q||!q.question_id||!q.question)return;currentRecallQuestion=q;document.getElementById('recall-question').textContent=q.question;document.getElementById('recall-answer').value='';document.getElementById('recall-feedback').textContent='';document.getElementById('recall-panel').style.display='block';document.getElementById('recall-submit').disabled=false;}
  async function submitRecall(){if(!currentRecallQuestion||!currentJobId)return;const input=document.getElementById('recall-answer');const answer=input.value.trim();if(!answer){document.getElementById('recall-feedback').textContent='Enter an answer first.';return;}const btn=document.getElementById('recall-submit');btn.disabled=true;document.getElementById('recall-feedback').textContent='Checking...';try{const res=await apiFetch('/videos/'+currentJobId+'/recall-response',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({student_id:getSetting('studentId','local-student'),question_id:currentRecallQuestion.question_id,answer_given:answer})});const data=await res.json();if(!res.ok)throw new Error(data.detail||'Could not record answer.');document.getElementById('recall-feedback').textContent=data.correct?'Correct. Nice work.':'Not quite. Your answer was recorded for a later recap.';document.getElementById('recall-feedback').style.color=data.correct?'var(--green)':'#f59e0b';}catch(err){btn.disabled=false;document.getElementById('recall-feedback').textContent=err.message||'Could not submit answer.';document.getElementById('recall-feedback').style.color='#ff8aaa';}}
  function onJobError(job){appendLog('  [ERROR] '+(job.error||'Unknown'));showError(job.error||'Unknown error');addAiMessage('❌ Render failed. Check Build Logs.',null,null);const sendBtn=document.getElementById('send-btn');sendBtn.disabled=false;sendBtn.style.opacity='1';}
  function showProgressOverlay(){document.getElementById('main-video-container').style.display='none';document.getElementById('recall-panel').style.display='none';document.getElementById('err-banner').classList.remove('visible');document.getElementById('script-preview').style.display='none';document.getElementById('scene-list').innerHTML='';document.getElementById('prog-bar').style.width='0%';document.getElementById('prog-pct').textContent='0%';document.getElementById('prog-msg').textContent='Starting...';STEPS.forEach(s=>{const el=document.getElementById('pstep-'+s);if(el)el.className='prog-step';});document.getElementById('progress-overlay').classList.add('visible');document.querySelectorAll('.vtab')[0].click();}
  function showError(msg){document.getElementById('err-banner').classList.add('visible');document.getElementById('err-text').textContent=msg;document.getElementById('progress-overlay').classList.remove('visible');}
  function appendLog(line){const el=document.getElementById('log-display');el.textContent+=line+'\n';el.parentElement.scrollTop=el.parentElement.scrollHeight;}
  const vid=document.getElementById('main-video');
  vid.addEventListener('timeupdate',()=>{const pct=(vid.currentTime/vid.duration)*100||0;document.getElementById('vid-progress').style.width=pct+'%';const fmt=t=>Math.floor(t/60)+':'+String(Math.floor(t%60)).padStart(2,'0');document.getElementById('vid-time').textContent=fmt(vid.currentTime)+' / '+fmt(vid.duration||0);});
  function toggleVideoPlay(){if(vid.paused)vid.play();else vid.pause();}
  function seekVideo(e){const r=e.currentTarget.getBoundingClientRect();vid.currentTime=((e.clientX-r.left)/r.width)*vid.duration;}
  let muted=false;
  function toggleMute(){muted=!muted;vid.muted=muted;document.getElementById('mute-x').style.display=muted?'block':'none';document.getElementById('mute-x2').style.display=muted?'block':'none';}
  function fullscreenVideo(){if(vid.requestFullscreen)vid.requestFullscreen();}
  function addUserMessage(text){const msgs=document.getElementById('rp-msgs');const nn=getSetting('nickname',getSetting('displayName',''));const init=nn.charAt(0).toUpperCase()||'U';msgs.innerHTML+=`<div class="msg user"><div class="msg-avatar">${init}</div><div><div class="msg-bubble">${escHtml(text)}</div><div class="msg-time">${nowTime()}</div></div></div>`;scrollChat();}
  function addAiMessage(html,jobId,filename){const msgs=document.getElementById('rp-msgs');const pill=jobId?`<div class="render-pill" onclick="focusPreview()" style="margin-top:8px;"><div class="render-pill-header"><div class="render-pill-icon"><svg viewBox="0 0 24 24" fill="currentColor" width="13" height="13"><polygon points="5 3 19 12 5 21 5 3"/></svg></div><div class="render-pill-info"><div class="render-pill-name">${escHtml(filename||'render.mp4')}</div><div class="render-pill-meta">Ready · ${currentFormat}</div></div><div class="render-pill-arrow"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="9 18 15 12 9 6"/></svg></div></div></div>`:'';msgs.innerHTML+=`<div class="msg ai"><div class="msg-avatar" style="background:linear-gradient(135deg,#00c3ff22,#0055ff22);border-color:rgba(0,195,255,0.3);color:var(--accent);">V</div><div><div class="msg-bubble">${html}${pill}</div><div class="msg-time">${nowTime()}</div></div></div>`;scrollChat();}
  function scrollChat(){const m=document.getElementById('rp-msgs');setTimeout(()=>m.scrollTop=m.scrollHeight,50);}
  function escHtml(t){if(!t)return'';return String(t).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');}
  function nowTime(){const n=new Date();return n.getHours()+':'+String(n.getMinutes()).padStart(2,'0');}
  function newChat(){if(pollInterval){clearInterval(pollInterval);pollInterval=null;}chatHistory=[];document.getElementById('rp-msgs').innerHTML=`<div class="msg ai"><div class="msg-avatar" style="background:linear-gradient(135deg,#00c3ff22,#0055ff22);border-color:rgba(0,195,255,0.3);color:var(--accent);">V</div><div><div class="msg-bubble">Hey! I'm <strong>Viva</strong>. What's on your mind? Ask anything, or type <code style="background:var(--bg-3);padding:1px 6px;border-radius:4px;">/video [topic]</code> to generate a video.</div><div class="msg-time">${nowTime()}</div></div></div>`;document.getElementById('main-video-container').style.display='none';document.getElementById('progress-overlay').classList.remove('visible');document.getElementById('err-banner').classList.remove('visible');document.getElementById('viewer-filename').textContent='No video yet';document.getElementById('log-display').textContent='';const sb=document.getElementById('send-btn');sb.disabled=false;sb.style.opacity='1';currentJobId=null;currentVideoUrl=null;currentManimCode=null;currentSessionId=null;}
  // SETTINGS
  function openSettings(page){document.getElementById('settings-backdrop').classList.add('open');showSettingsPage(page||'general');loadSettingsValues();}
  function closeSettings(){document.getElementById('settings-backdrop').classList.remove('open');}
  function closeSettingsIfBackdrop(e){if(e.target===document.getElementById('settings-backdrop'))closeSettings();}
  function showSettingsPage(page){document.querySelectorAll('.settings-page').forEach(p=>p.classList.remove('active'));document.querySelectorAll('.settings-nav-item').forEach(n=>n.classList.remove('active'));document.getElementById('spage-'+page)?.classList.add('active');document.getElementById('snav-'+page)?.classList.add('active');}
  function filterSettings(q){document.querySelectorAll('.settings-nav-item').forEach(item=>item.style.display=item.textContent.toLowerCase().includes(q.toLowerCase())?'flex':'none');}
  function loadSettingsValues(){const s=JSON.parse(localStorage.getItem('viv_settings')||'{}');if(s.projName)document.getElementById('s-proj-name').value=s.projName;if(s.backendUrl)document.getElementById('s-backend-url').value=s.backendUrl;if(s.displayName)document.getElementById('s-display-name').value=s.displayName;if(s.nickname)document.getElementById('s-nickname').value=s.nickname;if(s.instructions)document.getElementById('s-instructions').value=s.instructions;loadMemoryTags();try{const u=JSON.parse(sessionStorage.getItem('googleUser')||'{}');if(u.email)document.getElementById('s-email').value=u.email;if(u.name&&!document.getElementById('s-display-name').value)document.getElementById('s-display-name').value=u.name;}catch(_){}}
  function applyGeneralSettings(){const p=document.getElementById('s-proj-name').value.trim();if(p){document.getElementById('proj-name').textContent=p;saveSetting('projName',p);}toast('✓ Settings saved');closeSettings();}
  function applyProfileSettings(){saveSetting('displayName',document.getElementById('s-display-name').value.trim());saveSetting('nickname',document.getElementById('s-nickname').value.trim());toast('✓ Profile saved');closeSettings();}
  function setAccentColor(hex,rgb,el){document.querySelectorAll('.color-swatch').forEach(s=>s.classList.remove('active'));el?.classList.add('active');applyAccentColor(hex,rgb);saveSetting('accent',hex);saveSetting('accentRgb',rgb);}
  function customColor(hex){const r=parseInt(hex.slice(1,3),16),g=parseInt(hex.slice(3,5),16),b=parseInt(hex.slice(5,7),16);setAccentColor(hex,r+','+g+','+b,null);}
  function applyAccentColor(hex,rgb){document.documentElement.style.setProperty('--accent',hex);document.documentElement.style.setProperty('--accent-dim','rgba('+rgb+',0.11)');document.documentElement.style.setProperty('--accent-rgb',rgb);}
  function setFont(f){['geist','inter','mono'].forEach(v=>document.getElementById('font-'+v)?.classList.toggle('active',v===f));const fm={'geist':"'GeistPixel','Inter',sans-serif",'inter':"'Inter',sans-serif",'mono':"'JetBrains Mono',monospace"};document.documentElement.style.setProperty('--font',fm[f]);saveSetting('font',f);}
  function setDensity(d){['normal','compact'].forEach(v=>document.getElementById('density-'+v)?.classList.toggle('active',v===d));document.querySelector('.rp-messages').style.gap=d==='compact'?'10px':'18px';saveSetting('density',d);}
  function loadMemoryTags(){const notes=JSON.parse(localStorage.getItem('viv_memory_notes')||'[]');const c=document.getElementById('memory-tags-container');if(!c)return;c.innerHTML='';notes.forEach((n,i)=>{const t=document.createElement('div');t.className='memory-tag';t.innerHTML=escHtml(n)+' <span style="cursor:pointer;color:var(--t3);" onclick="removeMemoryNote('+i+')">×</span>';c.appendChild(t);});}
  function addMemoryNote(){const inp=document.getElementById('memory-note-input');const n=inp.value.trim();if(!n)return;const notes=JSON.parse(localStorage.getItem('viv_memory_notes')||'[]');notes.push(n);localStorage.setItem('viv_memory_notes',JSON.stringify(notes));inp.value='';loadMemoryTags();}
  function removeMemoryNote(idx){const notes=JSON.parse(localStorage.getItem('viv_memory_notes')||'[]');notes.splice(idx,1);localStorage.setItem('viv_memory_notes',JSON.stringify(notes));loadMemoryTags();}
  function clearMemory(){if(!confirm('Clear all memory notes?'))return;localStorage.removeItem('viv_memory_notes');loadMemoryTags();toast('Memory cleared');}
  function saveMemorySettings(){saveSetting('instructions',document.getElementById('s-instructions').value);toast('✓ Memory saved');}
  function saveBackendSettings(){const url=document.getElementById('s-backend-url').value.trim();saveSetting('backendUrl',url);window.__BACKEND_URL__=url;toast('✓ Backend URL saved');closeSettings();}
  async function testBackend(){const url=(document.getElementById('s-backend-url').value.trim()||BASE_URL);const el=document.getElementById('backend-status');el.textContent='Testing...';el.style.color='var(--t3)';try{const res=await fetch(url+'/',{signal:AbortSignal.timeout(5000)});if(res.ok){el.textContent='✓ Connected';el.style.color='var(--green)';}else{el.textContent='⚠ Status '+res.status;el.style.color='#f59e0b';}}catch(_){el.textContent='✗ Cannot connect';el.style.color='#ff8aaa';}}
  // MOBILE NAV
  function mobileNav(view){document.querySelectorAll('.mob-nav-btn').forEach(b=>b.classList.remove('active'));document.getElementById('mob-'+view)?.classList.add('active');if(view==='chat'){closeMobilePanel();return;}if(view==='settings'){openSettings('general');return;}openMobilePanel(view);}
  function openMobilePanel(view){const panel=document.getElementById('mobile-panel'),content=document.getElementById('mobile-panel-content');const titles={history:'History',files:'Files',templates:'Templates'};document.getElementById('mobile-panel-title').textContent=titles[view]||view;const src=document.getElementById('view-'+view);if(src){const inner=src.querySelector('.history-panel-inner,.files-panel-inner,.templates-inner');content.innerHTML=inner?inner.innerHTML:'';content.querySelectorAll('.template-item').forEach(item=>{const title=item.querySelector('.template-item-title');if(title)item.onclick=()=>useTemplate(title.textContent);});}panel.classList.add('open');}
  function closeMobilePanel(){document.getElementById('mobile-panel').classList.remove('open');document.querySelectorAll('.mob-nav-btn').forEach(b=>b.classList.remove('active'));document.getElementById('mob-chat')?.classList.add('active');}
  function focusPreview(){document.querySelectorAll('.vtab')[0].click();}
  function renameProject(){const n=prompt('Project name:',document.getElementById('proj-name').textContent);if(n){document.getElementById('proj-name').textContent=n;saveSetting('projName',n);}}
  function showExport(){if(currentVideoUrl){const a=document.createElement('a');a.href=currentVideoUrl;a.download=document.getElementById('viewer-filename').textContent||'render.mp4';a.click();}else toast('No video yet.');}
  function shareWorkspace(){navigator.clipboard?.writeText(location.href);toast('Link copied!');}
  function downloadVideo(){showExport();}
  function copyLink(){if(currentVideoUrl){navigator.clipboard?.writeText(currentVideoUrl);toast('Video URL copied!');}else toast('No video yet.');}
  function toast(msg){const t=document.getElementById('toast');t.textContent=msg;t.style.opacity='1';clearTimeout(t._timer);t._timer=setTimeout(()=>t.style.opacity='0',3000);}
  window.addEventListener('DOMContentLoaded', () => {
    document.getElementById('greeting-time').textContent = nowTime();
    loadSettings();
    try {
      const u = JSON.parse(sessionStorage.getItem('googleUser') || '{}');
      const av = document.getElementById('topbar-avatar');
      if (av && u.name) {
        av.title = u.email || u.name;
        if (u.picture) { av.style.backgroundImage = 'url(' + u.picture + ')'; av.style.backgroundSize = 'cover'; av.textContent = ''; } 
        else av.textContent = u.name.charAt(0).toUpperCase();
      }
    } catch (_) {}
    const p = new URLSearchParams(location.search).get('prompt');
    if (p) { document.getElementById('chat-input').value = p; sendMessage(); }
  });

