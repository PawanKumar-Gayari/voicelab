/* =========================================================
   CARD 2 — VOICE RESEARCH
   ========================================================= */

(function () {
    "use strict";

    const STATES = {
        READY: "ready",
        LISTENING: "listening",
        SPEAKING: "speaking"
    };

    const labels = {
        ready: "Ready",
        listening: "Listening",
        speaking: "Speaking"
    };

    const api = {
        root: null,
        orb: null,
        state: null,
        connection: null,
        transcript: null,
        empty: null,
        clearButton: null,
        currentState: STATES.READY,

        init() {
            this.root = document.getElementById("voice-research-card") || document.getElementById("voice-research");
            if (!this.root) return;

            this.orb = this.root.querySelector("#voice-orb");
            this.state = this.root.querySelector("#voice-state");
            this.connection = this.root.querySelector("#voice-connection-text");
            this.transcript = this.root.querySelector("#transcript");
            this.empty = this.root.querySelector("#empty-transcript");
            this.clearButton = this.root.querySelector("#clear-conversation");

            this.bindEvents();
            this.setState(STATES.READY);
            this.updateEmpty();
        },

        bindEvents() {
            this.orb?.addEventListener("click", () => {
                document.dispatchEvent(
                    new CustomEvent("voicelab:voice-click")
                );
            });

            this.clearButton?.addEventListener(
                "click",
                () => this.clear()
            );

            document.addEventListener(
                "voicelab:ready",
                () => this.setState(STATES.READY)
            );

            document.addEventListener(
                "voicelab:listening",
                () => this.setState(STATES.LISTENING)
            );

            document.addEventListener(
                "voicelab:speaking",
                () => this.setState(STATES.SPEAKING)
            );

            document.addEventListener(
                "voicelab:user-message",
                event => {
                    const text = event.detail?.text;
                    if (text) this.addMessage("user", text);
                }
            );

            document.addEventListener(
                "voicelab:assistant-message",
                event => {
                    const text = event.detail?.text;
                    if (text) this.addMessage("assistant", text);
                }
            );
        },

        setState(state) {
            if (!Object.values(STATES).includes(state)) {
                state = STATES.READY;
            }

            this.currentState = state;

            this.root.classList.remove(
                "voice-ready",
                "voice-listening",
                "voice-speaking"
            );

            this.root.classList.add(`voice-${state}`);

            this.orb?.classList.remove(
                "ready",
                "listening",
                "speaking"
            );

            this.orb?.classList.add(state);

            if (this.state) {
                this.state.textContent = labels[state];
            }

            document.dispatchEvent(
                new CustomEvent("voicelab:statechange", {
                    detail: { state }
                })
            );
        },

        addMessage(role, text) {
            if (!this.transcript || !text) return null;

            this.empty && (this.empty.style.display = "none");

            const message = document.createElement("div");
            message.className = "voice-message " +
                (role === "user"
                    ? "voice-message-user"
                    : "voice-message-assistant");

            const roleElement = document.createElement("div");
            roleElement.className = "voice-message-role";
            roleElement.textContent =
                role === "user" ? "You" : "VoiceLab";

            const textElement = document.createElement("div");
            textElement.className = "voice-message-text";
            textElement.textContent = String(text);

            message.append(roleElement, textElement);
            this.transcript.appendChild(message);

            requestAnimationFrame(() => {
                this.transcript.scrollTop =
                    this.transcript.scrollHeight;
            });

            return message;
        },

        addUserMessage(text) {
            return this.addMessage("user", text);
        },

        addAssistantMessage(text) {
            return this.addMessage("assistant", text);
        },

        clear() {
            this.transcript
                ?.querySelectorAll(".voice-message")
                .forEach(message => message.remove());

            this.updateEmpty();

            document.dispatchEvent(
                new CustomEvent("voicelab:conversation-cleared")
            );
        },

        updateEmpty() {
            if (!this.empty || !this.transcript) return;

            const hasMessages =
                this.transcript.querySelector(".voice-message");

            this.empty.style.display =
                hasMessages ? "none" : "flex";
        }
    };

    window.VoiceResearch = api;

    /* Compatibility helpers for existing VoiceLab code */
    window.setVoiceState = state => api.setState(state);
    window.addUserMessage = text => api.addUserMessage(text);
    window.addVoiceMessage = text => api.addAssistantMessage(text);
    window.clearVoiceConversation = () => api.clear();

    if (document.readyState === "loading") {
        document.addEventListener(
            "DOMContentLoaded",
            () => api.init(),
            { once: true }
        );
    } else {
        api.init();
    }
})();
