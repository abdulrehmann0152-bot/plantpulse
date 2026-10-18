"""A 'Copy to clipboard' button. Runs in a small iframe; falls back to the old execCommand method if the
browser blocks navigator.clipboard. The text is passed as JSON so any character is safe."""
import json

from core import animation

PAGE = """<!doctype html><html><head><meta charset="utf-8"><style>
body{margin:0;font-family:Arial,sans-serif;display:flex;align-items:center;gap:10px;height:40px}
button{font-size:14px;padding:7px 14px;border:1px solid #13A89E;border-radius:8px;background:#fff;color:#0B2545;cursor:pointer}
button:hover{background:#E8F7F5}
#msg{font-size:13px}
</style></head><body><button id="b" type="button">__LABEL__</button><span id="msg"></span>
<script>(function(){var T=__PAYLOAD__,b=document.getElementById('b'),m=document.getElementById('msg');
function done(ok){m.textContent=ok?'Copied!':'Could not copy. Use the text box below.';m.style.color=ok?'#2E9E5B':'#D64550';setTimeout(function(){m.textContent='';},3000);}
function fallback(){var t=document.createElement('textarea');t.value=T;t.style.position='fixed';t.style.opacity='0';document.body.appendChild(t);t.focus();t.select();var ok=false;try{ok=document.execCommand('copy');}catch(e){}document.body.removeChild(t);done(ok);}
b.onclick=function(){if(navigator.clipboard&&navigator.clipboard.writeText){navigator.clipboard.writeText(T).then(function(){done(true);},fallback);}else{fallback();}};})();</script>
</body></html>"""


def copy_button_html(text, label="Copy results to clipboard"):
    payload = json.dumps(text).replace("</", "<\\/")      # a '</script>' inside the text can never end the script early
    return PAGE.replace("__PAYLOAD__", payload).replace("__LABEL__", label)


def show_copy_button(text, label="Copy results to clipboard", height=46):
    animation.show(copy_button_html(text, label), height)
