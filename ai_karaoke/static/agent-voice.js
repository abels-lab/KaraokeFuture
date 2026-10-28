// Voice DJ: the Co-Pilot's 🎤 button turns speech into a chat message (browser speech
// recognition; Chrome / Edge / Safari). While listening the button glows red; when you stop
// talking the words are sent like a typed message. Browsers without it get a greyed-out button.
// Split from agent.js. Needs the Co-Pilot markup (host/markup-left.js).
// AgentVoice.init({ button, input, form })
const AgentVoice = (() => {
  const LISTENING = ["bg-red-600", "text-white", "animate-pulse"], IDLE = ["bg-white/10", "text-stone-300"];

  function init({ button, input, form }) {
    const SpeechRec = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!button) return;
    if (!SpeechRec) {
      button.classList.add("opacity-30", "cursor-not-allowed");
      button.title = "Voice recognition not supported by this browser";
      return;
    }
    const recognition = new SpeechRec();
    let listening = false;
    recognition.continuous = false;
    recognition.interimResults = true;
    recognition.lang = navigator.language || "en-US";
    const paint = (on) => {
      listening = on;
      button.classList.remove(...(on ? IDLE : LISTENING));
      button.classList.add(...(on ? LISTENING : IDLE));
    };

    recognition.onstart = () => paint(true);
    recognition.onresult = (ev) => {
      let transcript = "";
      for (let i = ev.resultIndex; i < ev.results.length; ++i) transcript += ev.results[i][0].transcript;
      input.value = transcript;
    };
    recognition.onend = () => {
      paint(false);
      if (input.value.trim()) form.requestSubmit();
    };
    recognition.onerror = () => paint(false);

    button.onclick = () => {
      if (listening) recognition.stop();
      else {
        input.value = "";
        recognition.start();
      }
    };
  }
  return { init };
})();
