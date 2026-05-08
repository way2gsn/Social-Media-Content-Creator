'use client';
import { useState, useEffect } from 'react';
import { Sparkles, Newspaper, History, Download, Layers, AlertCircle, Settings, Calendar, Clock, Trash2, Send, Play } from 'lucide-react';

const API = typeof window !== 'undefined' ? `${window.location.protocol}//${window.location.hostname}:8000` : 'http://localhost:8000';

export default function Home() {
  const [topics, setTopics] = useState('');
  const [count, setCount] = useState(3);
  const [activeTask, setActiveTask] = useState<string|null>(null);
  const [taskStatus, setTaskStatus] = useState<any>(null);
  const [gallery, setGallery] = useState([]);
  const [activeTab, setActiveTab] = useState('create');
  const [selectedPost, setSelectedPost] = useState<any>(null);
  const [language, setLanguage] = useState('english');
  const [isSettingsOpen, setIsSettingsOpen] = useState(false);
  const [isUploading, setIsUploading] = useState(false);
  const [settings, setSettings] = useState<any>({});
  const [isSaving, setIsSaving] = useState(false);
  const [schedules, setSchedules] = useState<any[]>([]);
  const [scheduleModal, setScheduleModal] = useState<any>(null);
  const [scheduleTime, setScheduleTime] = useState('');
  const [serverVersion, setServerVersion] = useState<string>('...');

  useEffect(() => {
    let iv: any;
    if (activeTask) {
      iv = setInterval(async () => {
        try {
          const r = await fetch(`${API}/task/${activeTask}`);
          const d = await r.json();
          setTaskStatus(d);
          if (d.status === 'Success' || d.status === 'Error') { clearInterval(iv); fetchGallery(); }
        } catch {}
      }, 2000);
    }
    return () => clearInterval(iv);
  }, [activeTask]);

  const fetchGallery = async () => { try { const r = await fetch(`${API}/gallery`); const d = await r.json(); setGallery(d.posts || []); } catch {} };
  const fetchSettings = async () => { try { const r = await fetch(`${API}/settings`); setSettings(await r.json()); } catch {} };
  const fetchSchedules = async () => { try { const r = await fetch(`${API}/schedules`); const d = await r.json(); setSchedules(d.schedules || []); } catch {} };

  const saveSettings = async (newSettings: any) => {
    setIsSaving(true);
    try {
      const merged = { ...settings, ...newSettings };
      const r = await fetch(`${API}/settings`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(merged)
      });
      if (r.ok) {
        setSettings(merged);
        setIsSettingsOpen(false);
      }
    } catch (err) {
      console.error("Save failed:", err);
    } finally {
      setIsSaving(false);
    }
  };

  const handleAudioUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    if (!e.target.files?.[0]) return;
    setIsUploading(true);
    const formData = new FormData();
    formData.append('file', e.target.files[0]);
    try {
      const res = await fetch(`${API}/upload-audio`, {
        method: 'POST',
        body: formData
      });
      if (res.ok) fetchSettings();
    } catch (err) {
      console.error("Upload failed", err);
    } finally {
      setIsUploading(false);
    }
  };

  const deleteAudio = async (filename: string) => {
    if (!confirm(`Delete ${filename}?`)) return;
    try {
      const res = await fetch(`${API}/audio/${filename}`, { method: 'DELETE' });
      if (res.ok) fetchSettings();
    } catch (err) {
      console.error("Delete failed", err);
    }
  };

  useEffect(() => { 
    fetchGallery(); 
    fetchSettings(); 
    fetchSchedules();
    const checkVersion = async () => {
      try {
        const r = await fetch(`${API}/version`);
        const d = await r.json();
        setServerVersion(d.version);
      } catch { setServerVersion('Offline'); }
    };
    checkVersion();
  }, []);

  const handleGenerate = async (endpoint: string) => {
    const fd = new FormData();
    fd.append('topics', topics); fd.append('count', count.toString()); fd.append('language', language);
    try { const r = await fetch(`${API}${endpoint}`, { method: 'POST', body: fd }); const d = await r.json(); setActiveTask(d.task_id); setActiveTab('create'); } catch {}
  };

  const handleSchedule = async () => {
    if (!scheduleModal || !scheduleTime) return;
    const fd = new FormData();
    fd.append('post_id', scheduleModal.id); fd.append('scheduled_at', scheduleTime); fd.append('caption', scheduleModal.caption || '');
    try { await fetch(`${API}/schedule`, { method: 'POST', body: fd }); setScheduleModal(null); setScheduleTime(''); fetchSchedules(); } catch {}
  };

  const deleteSchedule = async (id: number) => {
    try { await fetch(`${API}/schedule/${id}`, { method: 'DELETE' }); fetchSchedules(); } catch {}
  };

  const handleDeletePost = async (id: number) => {
    if (!confirm("Are you sure you want to delete this post? This will permanently remove the file from the server.")) return;
    try {
      const res = await fetch(`${API}/delete_post/${id}`, { method: 'DELETE' });
      if (res.ok) {
        fetchGallery();
        setSelectedPost(null);
      } else {
        const errorData = await res.json();
        alert(`Delete failed: ${errorData.error || 'Unknown error'}`);
      }
    } catch (err) {
      console.error("Delete failed", err);
    }
  };

  const navItems = [
    { id: 'create', label: 'Create', icon: Sparkles },
    { id: 'cinematic', label: 'Cinematic', icon: Play },
    { id: 'gallery', label: 'Gallery', icon: History },
    { id: 'templates', label: 'Templates', icon: Layers },
    { id: 'schedule', label: 'Schedule', icon: Calendar },
  ];

  return (
    <div className="min-h-screen bg-[#05070a] text-slate-200 font-sans selection:bg-amber-500/30">
      <nav className="fixed left-0 top-0 h-full w-64 bg-[#0a0d14] border-r border-white/5 p-8 flex flex-col z-50">
        <div className="mb-12 px-2">
          <h1 className="text-2xl font-black tracking-tighter text-white uppercase italic">Humorously <span className="text-amber-500">Indians</span></h1>
          <p className="text-[10px] uppercase tracking-[0.2em] font-bold text-slate-500 mt-1">AI Content Engine</p>
        </div>
        <div className="space-y-2 flex-1">
          {navItems.map(n => (
            <button key={n.id} onClick={() => { setActiveTab(n.id); if(n.id==='schedule') fetchSchedules(); }}
              className={`w-full flex items-center gap-3 px-4 py-3 rounded-xl transition-all ${activeTab===n.id ? 'bg-amber-500/10 text-amber-500 border border-amber-500/20' : 'text-slate-500 hover:text-white hover:bg-white/5'}`}>
              <n.icon size={18}/><span className="text-sm font-bold uppercase tracking-wider">{n.label}</span>
            </button>
          ))}
          <button onClick={() => { fetchSettings(); setIsSettingsOpen(true); }}
            className="w-full flex items-center gap-3 px-4 py-3 rounded-xl text-slate-500 hover:text-white hover:bg-white/5 transition-all">
            <Settings size={18}/><span className="text-sm font-bold uppercase tracking-wider">Settings</span>
          </button>
        </div>
        {activeTask && taskStatus && taskStatus.status !== 'Success' && taskStatus.status !== 'Error' && (
          <div className="mt-auto p-4 rounded-2xl bg-white/5 border border-white/10">
            <div className="flex justify-between items-center mb-2">
              <span className="text-[10px] font-bold uppercase text-amber-500">{taskStatus.status}</span>
              <span className="text-[10px] text-slate-500">{taskStatus.progress}%</span>
            </div>
            <div className="h-1 w-full bg-white/10 rounded-full overflow-hidden"><div className="h-full bg-amber-500 transition-all duration-500" style={{width:`${taskStatus.progress}%`}}/></div>
          </div>
        )}
        {/* Version Badge */}
        <div className="mt-4 p-4 pt-8 border-t border-white/5 opacity-50 hover:opacity-100 transition-opacity">
          <div className="flex items-center gap-3 px-4 py-3 bg-white/5 rounded-2xl border border-white/10">
            <div className="w-2 h-2 rounded-full bg-emerald-500 shadow-[0_0_8px_rgba(16,185,129,0.5)] animate-pulse" />
            <span className="text-[10px] font-black text-slate-400 uppercase tracking-[0.2em]">
              v1.8.1 (Server: {serverVersion})
            </span>
          </div>
        </div>
      </nav>

      <main className="pl-64 p-12 max-w-7xl mx-auto">
        {/* ── CREATE TAB ── */}
        {activeTab === 'create' && (
          <div className="space-y-8 animate-in fade-in duration-700">
            <header><h2 className="text-4xl font-extrabold text-white mb-2 tracking-tight">Production Studio</h2><p className="text-slate-500">Create high-impact social content.</p></header>
            <div className="grid grid-cols-1 lg:grid-cols-12 gap-8 items-start">
              <div className="lg:col-span-8 space-y-6">
                <div className="p-8 rounded-[32px] bg-white/[0.02] border border-white/10 backdrop-blur-3xl shadow-2xl">
                  <label className="text-[10px] uppercase font-black text-slate-500 tracking-[0.25em] mb-4 block">Topic / News Context</label>
                  <textarea value={topics} onChange={e=>setTopics(e.target.value)} placeholder="Describe the news or paste a headline..."
                    className="w-full bg-black/40 border border-white/5 rounded-2xl p-6 text-white text-lg placeholder:text-slate-700 focus:outline-none focus:border-amber-500/50 transition-all h-48 resize-none"/>
                  <div className="mt-8 pt-8 border-t border-white/5 grid grid-cols-3 gap-4">
                    <button onClick={()=>handleGenerate('/generate')} className="h-20 bg-white text-black font-black uppercase tracking-widest text-[10px] rounded-2xl hover:bg-slate-200 transition-all flex flex-col items-center justify-center gap-2 group">
                      <Newspaper size={22} className="group-hover:scale-110 transition-transform"/>Standard Post
                    </button>
                    <button onClick={()=>handleGenerate('/generate-carousel')} className="h-20 bg-amber-500 text-black font-black uppercase tracking-widest text-[10px] rounded-2xl hover:bg-amber-400 transition-all flex flex-col items-center justify-center gap-2 group shadow-[0_0_40px_rgba(245,158,11,0.15)]">
                      <Layers size={22} className="group-hover:scale-110 transition-transform"/>Carousel
                    </button>
                    <button onClick={()=>handleGenerate('/generate-quote')} className="h-20 bg-[#d97706] text-black font-black uppercase tracking-widest text-[10px] rounded-2xl hover:bg-[#b45309] hover:text-white transition-all flex flex-col items-center justify-center gap-2 group shadow-[0_0_40px_rgba(217,119,6,0.2)]">
                      <Sparkles size={22} className="group-hover:scale-110 transition-transform"/>Quote Post
                    </button>
                  </div>
                </div>
                {activeTask && taskStatus && (
                  <div className="p-6 rounded-3xl bg-black/40 border border-white/5 h-48 flex flex-col">
                    <h3 className="text-[9px] uppercase font-black text-slate-600 tracking-widest mb-3">Live Logs</h3>
                    <div className="flex-1 overflow-y-auto space-y-1.5 pr-4 custom-scrollbar font-mono text-[11px]">
                      {taskStatus.logs.map((log:string,i:number) => (
                        <div key={i} className="text-slate-500 flex gap-3">
                          <span className="text-amber-500/30 whitespace-nowrap">[{new Date().toLocaleTimeString([],{hour:'2-digit',minute:'2-digit'})}]</span>
                          <span className={log.includes('ERROR')?'text-red-400':log.includes('success')?'text-emerald-500/70':''}>{log}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
              <div className="lg:col-span-4 space-y-6">
                <div className="p-6 rounded-3xl bg-white/[0.02] border border-white/10">
                  <h3 className="text-[10px] uppercase font-black text-slate-500 tracking-[0.2em] mb-6">Config</h3>
                  <div className="space-y-6">
                    <div>
                      <label className="text-[9px] uppercase font-bold text-slate-600 mb-3 block">Language</label>
                      <div className="grid grid-cols-3 bg-black/40 border border-white/5 rounded-xl p-1 gap-1">
                        {['english','hindi','hinglish'].map(l=>(
                          <button key={l} onClick={()=>setLanguage(l)} className={`py-2.5 rounded-lg text-[10px] font-black uppercase transition-all ${language===l?'bg-white text-black':'text-slate-500 hover:text-white'}`}>
                            {l==='english'?'EN':l==='hindi'?'HI':'HG'}
                          </button>
                        ))}
                      </div>
                    </div>
                    <div>
                      <label className="text-[9px] uppercase font-bold text-slate-600 mb-3 block">Batch Count</label>
                      <div className="flex items-center gap-4 bg-black/40 border border-white/5 rounded-xl px-4 py-3">
                        <input type="range" min="1" max="10" value={count} onChange={e=>setCount(Number(e.target.value))} className="flex-1 accent-amber-500 h-1"/>
                        <span className="text-sm font-black text-white w-6 text-center">{count}</span>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* ── CINEMATIC TAB ── */}
        {activeTab === 'cinematic' && (
          <div className="space-y-8 animate-in fade-in duration-700">
            <header><h2 className="text-4xl font-extrabold text-white mb-2 tracking-tight">Cinematic Video Studio</h2><p className="text-slate-500">Generate professional documentary-style AI videos.</p></header>
            <div className="grid grid-cols-1 lg:grid-cols-12 gap-8 items-start">
              <div className="lg:col-span-8 space-y-6">
                <div className="p-8 rounded-[32px] bg-white/[0.02] border border-white/10 backdrop-blur-3xl shadow-2xl relative overflow-hidden">
                  <div className="absolute top-0 right-0 p-4 opacity-10">
                    <Play size={120} />
                  </div>
                  <label className="text-[10px] uppercase font-black text-slate-500 tracking-[0.25em] mb-4 block">Video Topic / Script Concept</label>
                  <textarea value={topics} onChange={e=>setTopics(e.target.value)} placeholder="E.g., The truth about Indian elections, or the hidden economics of street food..."
                    className="w-full bg-black/40 border border-white/5 rounded-2xl p-6 text-white text-lg placeholder:text-slate-700 focus:outline-none focus:border-emerald-500/50 transition-all h-48 resize-none relative z-10"/>
                  <div className="mt-8 pt-8 border-t border-white/5">
                    <button onClick={()=>handleGenerate('/generate-cinematic')} className="w-full h-20 bg-emerald-600 text-white font-black uppercase tracking-widest text-xs rounded-2xl hover:bg-emerald-500 transition-all flex items-center justify-center gap-3 shadow-[0_0_40px_rgba(16,185,129,0.2)]">
                      <Play size={24} /> Generate Full Cinematic Video
                    </button>
                  </div>
                </div>
                {activeTask && taskStatus && (
                  <div className="p-6 rounded-3xl bg-black/40 border border-white/5 h-48 flex flex-col">
                    <h3 className="text-[9px] uppercase font-black text-slate-600 tracking-widest mb-3">Live Video Production Logs</h3>
                    <div className="flex-1 overflow-y-auto space-y-1.5 pr-4 custom-scrollbar font-mono text-[11px]">
                      {taskStatus.logs.map((log:string,i:number) => (
                        <div key={i} className="text-slate-500 flex gap-3">
                          <span className="text-emerald-500/30 whitespace-nowrap">[{new Date().toLocaleTimeString([],{hour:'2-digit',minute:'2-digit'})}]</span>
                          <span className={log.includes('ERROR')?'text-red-400':log.includes('success')?'text-emerald-500/70':''}>{log}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
              <div className="lg:col-span-4 space-y-6">
                <div className="p-6 rounded-3xl bg-white/[0.02] border border-emerald-500/20">
                  <h3 className="text-[10px] uppercase font-black text-emerald-500 tracking-[0.2em] mb-4">Powered By</h3>
                  <div className="space-y-4 text-xs font-medium text-slate-400">
                    <div className="flex items-center gap-3"><Sparkles size={14} className="text-emerald-500"/> Gemini 2.5 Flash Scripting</div>
                    <div className="flex items-center gap-3"><Play size={14} className="text-emerald-500"/> Google TTS Journey Voices</div>
                    <div className="flex items-center gap-3"><Layers size={14} className="text-emerald-500"/> Veo 3.1 Lite Video Gen</div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* ── GALLERY TAB ── */}
        {activeTab === 'gallery' && (
          <div className="space-y-8 animate-in fade-in duration-700">
            <header className="flex justify-between items-end">
              <div><h2 className="text-4xl font-extrabold text-white mb-2 tracking-tight">Content Gallery</h2><p className="text-slate-500">Your generated content.</p></div>
              <button onClick={fetchGallery} className="text-[10px] font-bold uppercase text-amber-500 hover:text-white transition-colors">Refresh</button>
            </header>
            <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-6">
              {gallery.map((p:any)=>(
                <div key={p.id} onClick={()=>setSelectedPost(p)} className="group relative rounded-3xl cursor-pointer overflow-hidden border border-white/5 bg-white/[0.02] aspect-[4/5] hover:border-amber-500/30 transition-all duration-500">
                  {p.asset_path.endsWith('.mp4') ? (
                    <div className="w-full h-full bg-black flex items-center justify-center">
                        <Play size={40} className="text-white/20 group-hover:text-amber-500 transition-colors"/>
                        <video src={`${API}/static/output/${p.asset_path}`} className="absolute inset-0 w-full h-full object-cover opacity-60 group-hover:opacity-100 transition-opacity" muted loop playsInline onMouseEnter={e=>e.currentTarget.play()} onMouseLeave={e=>{e.currentTarget.pause();e.currentTarget.currentTime=0;}}/>
                    </div>
                  ) : (
                    <img src={`${API}/static/output/${p.asset_path}`} className="w-full h-full object-cover transition-transform duration-700 group-hover:scale-110" alt={p.headline}/>
                  )}
                  <div className="absolute inset-0 bg-gradient-to-t from-black via-transparent to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-500 flex flex-col justify-end p-6">
                    <div className="absolute top-4 right-4 flex gap-2">
                       <button onClick={(e)=>{e.stopPropagation(); handleDeletePost(p.id);}} className="p-2 rounded-lg bg-red-500/10 border border-red-500/20 text-red-500 hover:bg-red-500 hover:text-white transition-all shadow-lg">
                         <Trash2 size={14}/>
                       </button>
                    </div>
                    <p className="text-[10px] uppercase font-bold text-amber-500 mb-1">{p.topic}</p>
                    <p className="text-sm font-bold text-white line-clamp-2">{p.headline}</p>
                    <button onClick={(e)=>{e.stopPropagation();setScheduleModal(p);setScheduleTime('');}} className="mt-3 flex items-center gap-2 text-[9px] uppercase font-black tracking-widest text-amber-500 bg-amber-500/10 border border-amber-500/20 px-3 py-2 rounded-lg hover:bg-amber-500 hover:text-black transition-all">
                      <Calendar size={12}/>Schedule
                    </button>
                  </div>
                </div>
              ))}
              {gallery.length===0&&(<div className="col-span-full py-32 text-center text-slate-600 uppercase tracking-widest text-xs font-bold border-2 border-dashed border-white/5 rounded-3xl">No posts yet</div>)}
            </div>
          </div>
        )}
        {/* ── TEMPLATES TAB ── */}
        {activeTab === 'templates' && (
          <div className="space-y-8 animate-in fade-in duration-700">
            <header>
              <h2 className="text-4xl font-extrabold text-white mb-2 tracking-tight uppercase italic">Template <span className="text-amber-500">Lab</span></h2>
              <p className="text-slate-500 uppercase tracking-widest text-[10px] font-bold">Preview our premium editorial design systems.</p>
            </header>
            
            <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
              {[
                { name: 'Premium Quote', desc: 'Rusty B&W aesthetic single post', style: 'QUOTE', color: 'text-[#d97706]' },
                { name: 'Explainer', desc: 'Thematic news multi-slide story', style: 'EXPLAINER', color: 'text-rose-500' },
                { name: 'Modern Editorial', desc: 'Clean, professional news layout', style: 'MODERN_EDITORIAL', color: 'text-cyan-500' },
                { name: 'Satire Studio', desc: 'Bureaucratic irony & spin', style: 'SATIRE', color: 'text-emerald-500' },
              ].map(t => (
                <div key={t.style} className="group relative bg-[#0a0d14] border border-white/5 rounded-[40px] p-8 hover:border-amber-500/30 transition-all duration-500 overflow-hidden">
                  <div className="absolute top-0 right-0 w-32 h-32 bg-amber-500/5 blur-3xl -mr-16 -mt-16 group-hover:bg-amber-500/10 transition-all"></div>
                  <div className="relative z-10">
                    <span className={`text-[10px] font-black uppercase tracking-[0.3em] ${t.color}`}>{t.style}</span>
                    <h3 className="text-2xl font-black text-white mt-2 mb-4 italic uppercase">{t.name}</h3>
                    <p className="text-slate-500 text-sm mb-8 leading-relaxed">{t.desc}</p>
                    
                    <div className="grid grid-cols-2 gap-4 opacity-40 group-hover:opacity-100 transition-opacity">
                       <div className="aspect-[4/5] bg-white/5 rounded-2xl border border-white/10 flex items-center justify-center overflow-hidden">
                          <span className="text-[10px] font-bold uppercase text-slate-700">Cover</span>
                       </div>
                       <div className="aspect-[4/5] bg-white/5 rounded-2xl border border-white/10 flex items-center justify-center">
                          <span className="text-[10px] font-bold uppercase text-slate-700">Insights</span>
                       </div>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* ── SCHEDULE TAB ── */}
        {activeTab === 'schedule' && (
          <div className="space-y-8 animate-in fade-in duration-700">
            <header className="flex justify-between items-end">
              <div><h2 className="text-4xl font-extrabold text-white mb-2 tracking-tight">Post Scheduler</h2><p className="text-slate-500">Manage your Instagram posting schedule.</p></div>
              <button onClick={fetchSchedules} className="text-[10px] font-bold uppercase text-amber-500 hover:text-white transition-colors">Refresh</button>
            </header>
            {schedules.length===0 ? (
              <div className="py-32 text-center text-slate-600 uppercase tracking-widest text-xs font-bold border-2 border-dashed border-white/5 rounded-3xl">No scheduled posts. Go to Gallery to schedule one.</div>
            ) : (
              <div className="space-y-4">
                {schedules.map((s:any)=>(
                  <div key={s.id} className="flex items-center gap-6 p-6 rounded-2xl bg-white/[0.02] border border-white/10">
                    <div className="w-16 h-16 rounded-xl overflow-hidden bg-black shrink-0 relative">
                        {s.asset_path.endsWith('.mp4') ? (
                           <video src={`${API}/static/output/${s.asset_path}`} className="w-full h-full object-cover"/>
                        ) : (
                           <img src={`${API}/static/output/${s.asset_path}`} className="w-full h-full object-cover"/>
                        )}
                    </div>
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-bold text-white truncate">{s.caption?.slice(0,60) || 'No caption'}</p>
                      <div className="flex items-center gap-2 mt-1">
                        <Clock size={12} className="text-amber-500"/>
                        <span className="text-[11px] text-slate-400">{new Date(s.scheduled_at).toLocaleString()}</span>
                      </div>
                    </div>
                    <div className="flex flex-col items-end gap-1">
                      <span className={`px-3 py-1 rounded-full text-[9px] font-black uppercase tracking-wider ${s.status==='pending'?'bg-amber-500/10 text-amber-500 border border-amber-500/20':s.status==='completed'?'bg-emerald-500/10 text-emerald-500 border border-emerald-500/20':'bg-red-500/10 text-red-400 border border-red-500/20'}`} title={s.error_message || ''}>
                        {s.status}
                      </span>
                      {s.status === 'failed' && s.error_message && (
                        <span className="text-[8px] text-red-500/80 max-w-[200px] leading-tight text-right break-words">{s.error_message}</span>
                      )}
                    </div>
                    {s.status==='pending'&&(
                      <button onClick={()=>deleteSchedule(s.id)} className="p-2 rounded-lg text-slate-500 hover:text-red-400 hover:bg-red-500/10 transition-all"><Trash2 size={16}/></button>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </main>

      {/* ── POST DETAIL MODAL ── */}
      {selectedPost && (
        <div className="fixed inset-0 z-[100] flex items-center justify-center p-6 bg-black/90 backdrop-blur-md animate-in fade-in duration-300">
          <div className="bg-[#0a0d14] border border-white/10 rounded-[40px] w-full max-w-5xl h-[80vh] flex overflow-hidden shadow-2xl relative">
            <button onClick={() => setSelectedPost(null)} className="absolute top-8 right-8 z-[110] p-3 bg-white/5 hover:bg-amber-500 hover:text-black rounded-full transition-all">
                <Trash2 size={20} className="rotate-45"/>
            </button>
                <div className="flex-1 bg-black flex items-center justify-center relative overflow-hidden group">
                  {selectedPost.asset_path.endsWith('.mp4') ? (
                    <video 
                      src={selectedPost.asset_path.startsWith('http') ? selectedPost.asset_path : `${API}/static/output/${selectedPost.asset_path.replace('static/output/', '').replace(/^\/+/, '')}`} 
                      controls 
                      className="max-h-full max-w-full object-contain" 
                    />
                  ) : (
                    <img 
                      src={selectedPost.asset_path.startsWith('http') ? selectedPost.asset_path : `${API}/static/output/${selectedPost.asset_path.replace('static/output/', '').replace(/^\/+/, '')}`} 
                      alt={selectedPost.headline} 
                      className="max-h-full max-w-full object-contain"
                      onError={(e) => {
                        // Final fallback for local development if the API prefix is causing issues
                        const target = e.target as HTMLImageElement;
                        if (!target.src.includes('localhost:3000')) {
                           target.src = `/static/output/${selectedPost.asset_path.replace('static/output/', '').replace(/^\/+/, '')}`;
                        }
                      }}
                    />
                  )}
                  <div className="absolute inset-0 bg-gradient-to-t from-black/60 to-transparent opacity-0 group-hover:opacity-100 transition-opacity flex items-end p-8">
                    <p className="text-white/60 text-[10px] font-mono tracking-tighter truncate">{selectedPost.asset_path}</p>
                  </div>
                </div>
            <div className="w-1/2 p-12 flex flex-col overflow-y-auto custom-scrollbar">
              <div className="mb-8">
                  <p className="text-[10px] uppercase font-black text-amber-500 tracking-[0.3em] mb-2">{selectedPost.topic}</p>
                  <h2 className="text-3xl font-black text-white leading-tight uppercase italic">{selectedPost.headline}</h2>
              </div>
              <div className="space-y-6 flex-1">
                <div className="p-6 rounded-3xl bg-white/[0.03] border border-white/5">
                  <p className="text-[10px] uppercase font-black text-slate-600 tracking-widest mb-4">AI Insight</p>
                  <p className="text-slate-400 leading-relaxed italic">{selectedPost.subtitle}</p>
                </div>
                <div className="p-6 rounded-3xl bg-white/[0.03] border border-white/5">
                  <p className="text-[10px] uppercase font-black text-slate-600 tracking-widest mb-4">Full Caption</p>
                  <pre className="text-slate-300 whitespace-pre-wrap font-sans text-sm leading-relaxed">{selectedPost.caption}</pre>
                </div>
              </div>
              <div className="mt-8 flex gap-4">
                <button onClick={() => { setScheduleModal(selectedPost); setSelectedPost(null); setScheduleTime(''); }} className="flex-1 py-4 bg-amber-500 text-black font-black uppercase tracking-widest text-[10px] rounded-2xl hover:bg-amber-400 transition-all flex items-center justify-center gap-2">
                  <Calendar size={14}/>Schedule Post
                </button>
                <button onClick={() => handleDeletePost(selectedPost.id)} className="p-4 bg-red-500/10 text-red-500 border border-red-500/20 rounded-2xl hover:bg-red-500 hover:text-white transition-all" title="Delete Post">
                  <Trash2 size={20}/>
                </button>
                <a href={`${API}/static/output/${selectedPost.asset_path}`} download className="p-4 bg-white/5 text-white rounded-2xl hover:bg-white/10 transition-all">
                  <Download size={20}/>
                </a>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* ── SCHEDULE MODAL ── */}
      {scheduleModal && (
        <div className="fixed inset-0 z-[120] flex items-center justify-center p-6 bg-black/80 backdrop-blur-sm">
          <div className="bg-[#0a0d14] border border-white/10 rounded-[32px] p-8 w-full max-w-md shadow-2xl animate-in zoom-in duration-300">
            <h3 className="text-xl font-black text-white mb-2 uppercase italic">Schedule Content</h3>
            <p className="text-xs text-slate-500 mb-8 uppercase tracking-widest">Post: {scheduleModal.headline}</p>
            
            <div className="space-y-6">
              <div>
                <label className="text-[9px] uppercase font-black text-slate-600 mb-2 block tracking-widest">Target Time</label>
                <input type="datetime-local" value={scheduleTime} onChange={e=>setScheduleTime(e.target.value)}
                  className="w-full bg-black/40 border border-white/5 rounded-xl p-4 text-white focus:outline-none focus:border-amber-500/50 transition-all"/>
              </div>
              <div className="flex gap-3">
                <button onClick={()=>setScheduleModal(null)} className="flex-1 py-4 bg-white/5 text-slate-500 font-bold uppercase tracking-widest text-[10px] rounded-xl hover:bg-white/10 transition-all">Cancel</button>
                <button onClick={handleSchedule} className="flex-1 py-4 bg-amber-500 text-black font-black uppercase tracking-widest text-[10px] rounded-xl hover:bg-amber-400 transition-all shadow-[0_0_30px_rgba(245,158,11,0.2)]">Confirm</button>
              </div>
            </div>
          </div>
        </div>
      )}
      
      {isSettingsOpen && (
        <div className="fixed inset-0 z-[300] flex items-center justify-center p-6 bg-black/90 backdrop-blur-xl animate-in fade-in duration-200">
          <div className="w-full max-w-lg bg-[#0d1117] rounded-[40px] border border-white/10 shadow-2xl overflow-hidden">
            <div className="p-10 border-b border-white/5 flex justify-between items-center">
              <div>
                <h3 className="text-2xl font-black text-white uppercase italic tracking-tighter">Settings</h3>
                <p className="text-xs text-slate-500 mt-1 uppercase tracking-widest font-bold">Content Engine</p>
              </div>
              <button onClick={()=>setIsSettingsOpen(false)} className="text-slate-500 hover:text-white p-2">
                <AlertCircle size={24} className="rotate-45"/>
              </button>
            </div>
            
            <div className="p-10 space-y-8">
              {/* Content Engine Switches */}
                <div className="flex items-center justify-between p-4 bg-white/20 rounded-xl border border-white/5">
                  <div>
                    <p className="text-xs font-bold text-white uppercase tracking-wider">Background Music</p>
                    <p className="text-[10px] text-slate-500">Convert standard posts to Reels with music</p>
                  </div>
                  <button onClick={() => saveSettings({use_music: settings.use_music === 'true' ? 'false' : 'true'})}
                    className={`w-12 h-6 rounded-full transition-all relative ${settings.use_music === 'true' ? 'bg-amber-500' : 'bg-white/10'}`}>
                    <div className={`absolute top-1 w-4 h-4 rounded-full bg-white transition-all ${settings.use_music === 'true' ? 'left-7' : 'left-1'}`}/>
                  </button>
                </div>

                <div className="flex items-center justify-between p-4 bg-white/20 rounded-xl border border-white/5">
                  <div>
                    <p className="text-xs font-bold text-white uppercase tracking-wider">Professional API Mode</p>
                    <p className="text-[10px] text-slate-500">Use Instagram Graph API (Recommended for GCP)</p>
                  </div>
                  <button onClick={() => saveSettings({scheduler_mode: settings.scheduler_mode === 'api' ? 'automation' : 'api'})}
                    className={`w-12 h-6 rounded-full transition-all relative ${settings.scheduler_mode === 'api' ? 'bg-emerald-500' : 'bg-white/10'}`}>
                    <div className={`absolute top-1 w-4 h-4 rounded-full bg-white transition-all ${settings.scheduler_mode === 'api' ? 'left-7' : 'left-1'}`}/>
                  </button>
                </div>

                <div className="flex items-center justify-between p-4 bg-amber-500/5 rounded-xl border border-amber-500/20">
                  <div>
                    <p className="text-xs font-bold text-amber-500 uppercase tracking-wider">Full-Auto Engine</p>
                    <p className="text-[10px] text-amber-500/60">Autonomous generation & random scheduling</p>
                  </div>
                  <button onClick={() => saveSettings({full_auto: settings.full_auto === 'true' ? 'false' : 'true'})}
                    className={`w-12 h-6 rounded-full transition-all relative ${settings.full_auto === 'true' ? 'bg-amber-500 shadow-[0_0_15px_rgba(245,158,11,0.5)]' : 'bg-white/10'}`}>
                    <div className={`absolute top-1 w-4 h-4 rounded-full bg-white transition-all ${settings.full_auto === 'true' ? 'left-7' : 'left-1'}`}/>
                  </button>
                </div>

              {/* Instagram API Tokens */}
              <div className="space-y-4">
                <p className="text-[10px] font-bold text-slate-600 uppercase tracking-[0.25em] mb-2">Instagram API Credentials</p>
                <div className="space-y-3">
                  <input 
                    type="text" 
                    placeholder="Access Token" 
                    value={settings.ig_access_token || ''} 
                    onChange={e => setSettings({...settings, ig_access_token: e.target.value})}
                    className="w-full bg-black/40 border border-white/5 rounded-xl p-4 text-xs text-white placeholder:text-slate-700 focus:outline-none focus:border-amber-500/50 transition-all"
                  />
                  <input 
                    type="text" 
                    placeholder="Business ID" 
                    value={settings.ig_business_id || ''} 
                    onChange={e => setSettings({...settings, ig_business_id: e.target.value})}
                    className="w-full bg-black/40 border border-white/5 rounded-xl p-4 text-xs text-white placeholder:text-slate-700 focus:outline-none focus:border-amber-500/50 transition-all"
                  />
                </div>
              </div>

              {/* Audio Library (Optional) */}
              {settings.use_music === 'true' && (
                <div className="p-4 bg-black/20 rounded-xl border border-white/5">
                  <div className="flex justify-between items-center mb-4">
                    <p className="text-[10px] font-bold text-slate-500 uppercase tracking-widest">Audio Library</p>
                    <label className={`cursor-pointer text-[10px] font-black uppercase tracking-widest px-3 py-1.5 rounded-lg transition-all ${isUploading ? 'bg-white/5 text-slate-600' : 'bg-amber-500 text-black hover:bg-amber-400'}`}>
                      {isUploading ? 'Uploading...' : 'Upload MP3'}
                      <input type="file" accept=".mp3,.wav,.m4a" className="hidden" onChange={handleAudioUpload} disabled={isUploading}/>
                    </label>
                  </div>
                  <div className="space-y-2 max-h-32 overflow-y-auto pr-2 custom-scrollbar">
                    {settings.available_tracks?.map((t:string) => (
                      <div key={t} className="flex justify-between items-center p-2 rounded-lg bg-white/5 group">
                        <span className="text-[10px] text-slate-400 truncate pr-4">{t}</span>
                        <button onClick={() => deleteAudio(t)} className="text-slate-600 hover:text-red-500 transition-colors opacity-0 group-hover:opacity-100 p-1">
                          <AlertCircle size={14} className="rotate-45"/>
                        </button>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>

            <div className="p-10 pt-0">
               <button 
                 onClick={() => saveSettings(settings)} 
                 className="w-full py-4 bg-amber-500 text-black font-black uppercase tracking-widest text-xs rounded-xl hover:bg-amber-400 transition-all shadow-[0_0_20px_rgba(245,158,11,0.3)]"
               >
                 {isSaving ? 'Saving to Cloud...' : 'Confirm & Save to Cloud'}
               </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
