const bubble = document.getElementById("bubble");

bubble.addEventListener("click", () => {
  window.codeDuck.openMainWindow();
});

window.codeDuck.onPresence((presence) => {
  const state = String((presence && presence.state) || "idle").toLowerCase();
  bubble.className = `bubble ${state}`;
  const status = presence && presence.status ? presence.status : "Open Neha";
  bubble.title = status;
  bubble.setAttribute("aria-label", status);
});
