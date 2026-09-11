/* VoiceLab integrated workspace bridge.
 *
 * The browser is a presentation layer only:
 * - LiveKit carries voice/transcript events.
 * - FastAPI session state is the authoritative persisted state.
 * - The scientific backend/registry decides the molecule and symmetry data.
 * - No molecule names, coordinates, point groups, or analysis results are
 *   hardcoded here.
 */
(function () {
    "use strict";

    const config = window.VoiceLabConfig || {};
    const sessionId = String(config.sessionId || "").trim();

    if (!sessionId) {
        console.error("[VoiceLab] Missing session_id.");
        return;
    }

    const orb = document.getElementById("voice-orb");
    const voiceState = document.getElementById("voice-state");
    const connectionText = document.getElementById("voice-connection-text");
    const connectionDot = document.getElementById("connection-dot");
    const textCommandForm = document.getElementById("text-command-form");
    const textCommandInput = document.getElementById("text-command-input");
    const textCommandSend = document.getElementById("text-command-send");
    const visionButton = document.getElementById("vision-screen");
    const visionResult = document.getElementById("vision-result");
    const replayButton = document.getElementById("replay-memory");
    const replayPanel = document.getElementById("replay-panel");
    const traceList = document.getElementById("agent-trace-list");

    let room = null;
    let microphoneActive = false;
    let reconnectTimer = null;
    let stateTimer = null;
    let intentionalClose = false;
    let lastStateFingerprint = "";

    function setConnection(message, state) {
        if (connectionText) connectionText.textContent = message;
        if (connectionDot) {
            connectionDot.classList.remove("connected", "connecting", "error");
            connectionDot.classList.add(state || "connecting");
        }
    }

    function setVoice(state, message) {
        const allowed = ["ready", "listening", "speaking", "processing"];
        const safeState = allowed.includes(state) ? state : "ready";

        if (voiceState) {
            voiceState.textContent = message || (
                safeState === "listening" ? "Listening..." :
                safeState === "speaking" ? "Speaking..." :
                safeState === "processing" ? "Processing..." : "Ready"
            );
        }

        if (orb) {
            orb.classList.remove("ready", "listening", "speaking", "processing");
            orb.classList.add(safeState);
        }
    }

    function dispatch(name, detail) {
        document.dispatchEvent(new CustomEvent(name, { detail }));
    }

    function trace(stage, message, ok = true) {
        if (!traceList) return;
        const item = document.createElement("div");
        item.className = "trace-item " + (ok ? "ok" : "fail");
        item.innerHTML = `<b>${escapeHtml(stage)}</b>${escapeHtml(message)}`;
        traceList.appendChild(item);
        while (traceList.children.length > 8) traceList.removeChild(traceList.firstChild);
    }

    function normalizeAtom(atom) {
        if (Array.isArray(atom)) {
            return {
                element: String(atom[0] || "X"),
                x: Number(atom[1]) || 0,
                y: Number(atom[2]) || 0,
                z: Number(atom[3]) || 0
            };
        }

        return {
            element: String(atom?.element || atom?.symbol || atom?.label || "X"),
            x: Number(atom?.x) || 0,
            y: Number(atom?.y) || 0,
            z: Number(atom?.z) || 0
        };
    }

    function coordinatesToAtoms(coordinates) {
        if (Array.isArray(coordinates)) {
            return coordinates.map(normalizeAtom);
        }

        if (!coordinates || typeof coordinates !== "object") {
            return [];
        }

        return Object.entries(coordinates).map(([label, value]) => {
            if (Array.isArray(value)) {
                return normalizeAtom([String(label).replace(/[0-9]+$/, ""), ...value]);
            }

            const atom = normalizeAtom(value);
            if (atom.element === "X") {
                atom.element = String(value?.element || value?.symbol || label).replace(/[0-9]+$/, "");
            }
            return atom;
        });
    }

    function moleculePayload(state) {
        const source = state?.molecule_data || {};
        const coordinates = source.coordinates ?? state?.coordinates ?? {};
        const atoms = Array.isArray(source.atoms) && source.atoms.length
            ? source.atoms.map(normalizeAtom)
            : coordinatesToAtoms(coordinates);

        if (!atoms.length) return null;

        return {
            id: source.id ?? state?.molecule ?? null,
            name: source.name ?? state?.molecule ?? null,
            formula: source.formula ?? null,
            pointGroup: source.point_group ?? state?.point_group ?? null,
            atoms,
            bonds: Array.isArray(source.bonds) ? source.bonds : [],
            operations: Array.isArray(state?.operations) ? state.operations : []
        };
    }

    function analysisPayload(state) {
        const groupTheory = state?.group_theory || {};
        const representation = state?.representation || {};

        const vibrationalAnalysis =
            state?.vibrational_analysis ||
            state?.vibrationalAnalysis ||
            null;

        const threeNReduction =
            vibrationalAnalysis?.representations?.["3n"]?.reduction ||
            representation?.reduction ||
            groupTheory?.reduction ||
            null;

        const reduction = threeNReduction || {};

        const characters =
            state?.characters ||
            representation?.characters ||
            groupTheory?.reducible_characters ||
            {};

        const operations = Array.isArray(state?.operations)
            ? state.operations
            : Array.isArray(state?.molecule_data?.operations)
                ? state.molecule_data.operations
                : [];

        const pointGroup =
            state?.point_group ||
            state?.molecule_data?.point_group ||
            groupTheory?.group ||
            null;

        const verification =
            state?.verification ||
            {};

        const symmetryVerification =
            state?.symmetry_verification ||
            {};

        const reductionData =
            Object.keys(reduction).length
                ? reduction
                : null;

        return {
            molecule:
                state?.molecule ||
                state?.molecule_data?.formula ||
                state?.molecule_data?.id ||
                null,

            pointGroup,

            operations,

            operationCount: operations.length,

            characters,

            reduction:
                reductionData,

            groupTheory,

            verification,

            symmetryVerification,

            representation,

            vibrational_analysis: vibrationalAnalysis,

            matrices:
                state?.matrices || {}
        };
    }


    function ensureReplayButton() {
        return;
        if (document.getElementById("research-replay-button")) return;

        const button = document.createElement("a");
        button.id = "research-replay-button";
        button.className = "workspace-replay-button";
        button.textContent = "Replay";
        button.href =
            "/research/replay/" + encodeURIComponent(sessionId);

        const candidates = [
            document.querySelector(".workspace-header"),
            document.querySelector(".topbar"),
            document.querySelector("header"),
            document.querySelector(".workspace")
        ];

        const target = candidates.find(Boolean);

        if (target) {
            target.appendChild(button);
        }
    }

function publishState(state) {
        if (!state || typeof state !== "object") return;

        const molecule = moleculePayload(state);
        if (molecule) {
            dispatch("voicelab:molecule-data", molecule);
            trace("STATE", `${molecule.formula || molecule.id || "Molecule"} geometry available`);
        }

        const analysis = analysisPayload(state);
        dispatch("voicelab:analysis-data", analysis);
        if (analysis.pointGroup && analysis.pointGroup !== "—") trace("RESULT", `Point group ${analysis.pointGroup}`);
        if (Array.isArray(analysis.operations) && analysis.operations.length) {
            const verified = analysis.operations.filter(op => op?.verified === true).length;
            if (verified) trace("VERIFICATION", `${verified}/${analysis.operations.length} operations verified`);
        }
    }

        ensureReplayButton();

async function refreshState() {
        try {
            const response = await fetch(
                "/api/sessions/" + encodeURIComponent(sessionId) +
                "?_=" + Date.now(),
                { cache: "no-store" }
            );

            if (!response.ok) return;

            const payload = await response.json();
            const state = payload?.state || payload?.research || payload;

            if (!state || typeof state !== "object") return;

            const fingerprint = JSON.stringify(state);
            if (fingerprint !== lastStateFingerprint) {
                lastStateFingerprint = fingerprint;
                publishState(state);
            }
        } catch (error) {
            console.debug("[VoiceLab] State refresh failed:", error);
        }
    }

    function decodeLiveKitPayload(payload) {
        try {
            if (typeof payload === "string") return JSON.parse(payload);
            return JSON.parse(new TextDecoder().decode(payload));
        } catch (_) {
            return null;
        }
    }

    function handleData(payload) {
        const event = decodeLiveKitPayload(payload);
        if (!event || typeof event !== "object") return;

        if (event.type === "transcript") {
            if (event.final === false) return;

            const role = String(event.role || "assistant").toLowerCase() === "user"
                ? "user"
                : "assistant";
            const text = String(event.text || "").trim();

            if (text) {
                dispatch(
                    role === "user"
                        ? "voicelab:user-message"
                        : "voicelab:assistant-message",
                    { text }
                );
            }
            return;
        }

        if (event.type === "voice_state") {
            setVoice(event.state, event.message);
            return;
        }

        if (event.type === "research_state" || event.type === "state") {
            const state = event.state || event.research || event;
            publishState(state);
            return;
        }

        if (event.type === "tool_status") {
            if (event.state === "running") {
                setVoice("processing", "Calculating...");
                trace((event.stage || "CALCULATION").toUpperCase(), `${event.tool || "tool"} running`);
            } else if (event.state === "completed") {
                trace((event.stage || "CALCULATION").toUpperCase(), `${event.tool || "tool"} complete`);
                refreshState();
            }
            return;
        }

        if (event.type === "molecule_action") {
            const action = String(event.action || "").trim();
            if (action) {
                dispatch("voicelab:molecule-action", { action });
                trace("ACTION", action + " displayed");
            }
            return;
        }

        if (event.type === "error") {
            console.error("[VoiceLab] Voice agent error:", event.message || event);
            trace("RECOVERY", "Voice service temporarily unavailable", false);
            setVoice(
                "processing",
                "Voice temporarily unavailable. You can continue with typed commands."
            );
        }
    }

    document.addEventListener("voicelab:molecule-viewer-action-result", async event => {
        const detail = event.detail || {};
        trace("ACTION", `${detail.action || "viewer action"} verified in browser`);
        try {
            const response = await fetch("/api/sessions/" + encodeURIComponent(sessionId) + "/viewer-state", {
                method: "POST",
                headers: {"Content-Type": "application/json"},
                body: JSON.stringify({
                    action: detail.action,
                    atom_labels: detail.atomLabels,
                    element_names: detail.elementNames,
                    highlight: detail.highlight || "none"
                })
            });
            if (!response.ok) trace("RECOVERY", "Viewer state report failed", false);
        } catch (_) {
            trace("RECOVERY", "Viewer state report failed", false);
        }
    });

    async function connectLiveKit() {
        if (!window.VoiceLabLiveKit) {
            throw new Error("LiveKit client bridge is unavailable.");
        }

        const roomName = "voicelab-" + sessionId;
        const identity = "researcher-" + sessionId;

        setConnection("Connecting", "connecting");
        setVoice("processing", "Joining voice room...");

        const response = await fetch(
            "/api/livekit/token?room=" +
            encodeURIComponent(roomName) +
            "&identity=" +
            encodeURIComponent(identity),
            { cache: "no-store" }
        );

        if (!response.ok) {
            let detail = "Unable to create LiveKit token.";
            try {
                const body = await response.json();
                detail = body.detail || detail;
            } catch (_) {}
            throw new Error(detail);
        }

        const data = await response.json();

        room = await VoiceLabLiveKit.connect({
            url: data.url || config.livekitUrl || "",
            token: data.token,
            onTrack: track => {
                if (track?.kind === "audio") {
                    setVoice("speaking", "Speaking...");
                }
            },
            onDisconnected: reason => {
                if (intentionalClose) return;

                console.warn("[VoiceLab] LiveKit disconnected:", reason);
                room = null;
                setConnection("Disconnected", "error");
                setVoice("processing", "Reconnecting...");

                clearTimeout(reconnectTimer);
                reconnectTimer = setTimeout(() => {
                    connectLiveKit().catch(handleConnectError);
                }, 1500);
            }
        });

        room.on(
            LivekitClient.RoomEvent.DataReceived,
            payload => handleData(payload)
        );

        setConnection("Connected", "connected");
        setVoice("ready", "Ready");

        await refreshState();

        clearInterval(stateTimer);
        stateTimer = setInterval(refreshState, 1200);
    }

    async function startMicrophone() {
        if (!room) {
            await connectLiveKit();
        }

        if (!room) return;

        try {
            // This click is a real user gesture. Use it to unlock browser
            // playback before the agent sends its first TTS audio.
            if (window.VoiceLabLiveKit?.startAudio) {
                await window.VoiceLabLiveKit.startAudio();
            }

            await room.localParticipant.setMicrophoneEnabled(true);
            microphoneActive = true;
            setVoice("listening", "Listening...");
        } catch (error) {
            console.error("[VoiceLab] Microphone error:", error);
            setVoice(
                "processing",
                error?.name === "NotAllowedError"
                    ? "Microphone permission denied"
                    : "Microphone unavailable"
            );
        }
    }

    async function stopMicrophone() {
        microphoneActive = false;

        if (room?.localParticipant) {
            try {
                await room.localParticipant.setMicrophoneEnabled(false);
            } catch (_) {}
        }

        setVoice("ready", "Ready");
    }

    function handleConnectError(error) {
        console.error("[VoiceLab] LiveKit connection failed:", error);
        setConnection("Voice unavailable", "error");
        setVoice(
            "processing",
            "Voice temporarily unavailable. You can continue with typed commands."
        );
    }

    orb?.addEventListener("click", async () => {
        if (microphoneActive) {
            await stopMicrophone();
        } else {
            try {
                await startMicrophone();
            } catch (error) {
                handleConnectError(error);
            }
        }
    });

    function renderVision(data) {
        if (!visionResult) return;
        const vision = data?.vision || {};
        const items = Array.isArray(vision.ui_elements) ? vision.ui_elements : [];
        const issues = Array.isArray(vision.issues) ? vision.issues : [];
        const actions = Array.isArray(vision.suggested_actions) ? vision.suggested_actions : [];
        visionResult.hidden = false;
        visionResult.innerHTML = `
            <strong>Screen Vision</strong><div>${escapeHtml(vision.summary || "Screen analyzed.")}</div>
            ${items.length ? `<div><b>Visible:</b><ul class="vision-list">${items.slice(0,8).map(x=>`<li>${escapeHtml(String(x))}</li>`).join("")}</ul></div>` : ""}
            ${issues.length ? `<div><b>Issues:</b><ul class="vision-list">${issues.slice(0,6).map(x=>`<li>${escapeHtml(String(x))}</li>`).join("")}</ul></div>` : ""}
            ${actions.length ? `<div><b>Suggested:</b> ${actions.slice(0,4).map(x=>escapeHtml(String(x))).join(" · ")}</div>` : ""}`;
    }

    function escapeHtml(value) {
        return String(value).replace(/[&<>'"]/g, ch => ({"&":"&amp;","<":"&lt;",">":"&gt;","'":"&#39;","\"":"&quot;"}[ch]));
    }

    async function analyzeVisibleScreen() {
        if (!navigator.mediaDevices?.getDisplayMedia) {
            throw new Error("Screen sharing is not supported in this browser.");
        }
        const stream = await navigator.mediaDevices.getDisplayMedia({video: {frameRate: 1}, audio: false});
        try {
            const video = document.createElement("video");
            video.srcObject = stream;
            video.muted = true;
            await video.play();
            await new Promise(resolve => setTimeout(resolve, 250));
            const canvas = document.createElement("canvas");
            const maxWidth = 1600;
            const scale = Math.min(1, maxWidth / video.videoWidth);
            canvas.width = Math.max(1, Math.round(video.videoWidth * scale));
            canvas.height = Math.max(1, Math.round(video.videoHeight * scale));
            canvas.getContext("2d").drawImage(video, 0, 0, canvas.width, canvas.height);
            const imageBase64 = canvas.toDataURL("image/jpeg", 0.78);
            const response = await fetch("/api/sessions/" + encodeURIComponent(sessionId) + "/vision", {
                method: "POST", headers: {"Content-Type":"application/json"},
                body: JSON.stringify({image_base64: imageBase64})
            });
            const payload = await response.json().catch(() => ({}));
            if (!response.ok || !payload.success) throw new Error(payload.detail || "Screen vision failed.");
            renderVision(payload);
            trace("VISION", "Workspace screen analyzed");
        } finally {
            stream.getTracks().forEach(track => track.stop());
        }
    }

    visionButton?.addEventListener("click", async () => {
        visionButton.disabled = true;
        visionButton.textContent = "Scanning…";
        try { await analyzeVisibleScreen(); }
        catch (error) { if (visionResult) { visionResult.hidden = false; visionResult.textContent = error?.message || "Screen vision failed."; } }
        finally { visionButton.disabled = false; visionButton.textContent = "Vision"; }
    });

    async function loadReplay() {
        if (!replayPanel) return;
        const response = await fetch("/api/sessions/" + encodeURIComponent(sessionId) + "/replay?_=" + Date.now(), {cache:"no-store"});
        const payload = await response.json();
        if (!response.ok || !payload.success) throw new Error(payload.detail || "Replay unavailable.");
        const events = Array.isArray(payload.events) ? payload.events : [];
        const verifications = Array.isArray(payload.verification_history) ? payload.verification_history : [];
        replayPanel.hidden = false;
        replayPanel.innerHTML = `<strong>Agent Memory · Replay</strong><div>${events.length ? events.slice(-40).map(e => `<div class="replay-event"><span class="replay-kind">${escapeHtml(e.kind || "event")}</span>${escapeHtml(e.text || e.tool || e.summary || JSON.stringify(e))}</div>`).join("") : "No replay events yet."}</div><div style="margin-top:6px"><strong>Verification audits:</strong> ${verifications.length}</div>`;
    }
    replayButton?.addEventListener("click", () => {
        window.location.href =
            "/research/replay/" + encodeURIComponent(sessionId);
    });

    async function submitTypedCommand() {
        const text = String(textCommandInput?.value || "").trim();
        if (!text) return;

        if (textCommandSend) textCommandSend.disabled = true;
        dispatch("voicelab:user-message", { text });
        setVoice("processing", "Processing...");

        try {
            const response = await fetch(
                "/api/sessions/" + encodeURIComponent(sessionId) + "/text",
                {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ text })
                }
            );
            const payload = await response.json().catch(() => ({}));
            if (!response.ok || !payload.success) {
                throw new Error(payload.detail || payload.message || "Typed command failed.");
            }

            if (payload.type === "molecule_action") {
                dispatch("voicelab:molecule-action", { action: payload.action });
                dispatch("voicelab:assistant-message", { text: "Done — the molecule viewer was updated." });
            } else {
                dispatch("voicelab:assistant-message", { text: payload.message || "Done." });
            }

            await refreshState();
        } catch (error) {
            console.error("[VoiceLab] Typed command failed:", error);

            /*
             * Never expose raw backend/tool errors to the user.
             * Scientific/tool diagnostics stay in the browser console;
             * the conversation receives a clean recovery message.
             */
            const raw = String(error?.message || "");
            let userMessage = "I could not complete that request.";

            if (/INVALID_OPERATIONS|operations must be a non-empty list/i.test(raw)) {
                userMessage =
                    "I need the molecule's symmetry operations before I can calculate the representation reduction. Preparing the required symmetry data…";
            } else if (/INVALID_|VALIDATION|validation error/i.test(raw)) {
                userMessage =
                    "I couldn't complete that calculation from the available scientific data. Please try the request again.";
            } else if (/timeout|timed out/i.test(raw)) {
                userMessage =
                    "The calculation took too long to complete. Please try again.";
            }

            dispatch("voicelab:assistant-message", { text: userMessage });
        } finally {
            if (textCommandInput) {
                textCommandInput.value = "";
                textCommandInput.focus();
            }
            if (textCommandSend) textCommandSend.disabled = false;
            setVoice("ready", "Ready");
        }
    }

    textCommandForm?.addEventListener("submit", event => {
        event.preventDefault();
        submitTypedCommand();
    });

    document.addEventListener("voicelab:conversation-cleared", () => {
        const transcript = document.getElementById("transcript");
        if (transcript) {
            transcript.querySelectorAll(".voice-message").forEach(node => node.remove());
        }
    });

    window.VoiceLabMainBridge = {
        refreshState,
        connectLiveKit,
        startMicrophone,
        stopMicrophone
    };

    // Start the LiveKit connection immediately. The microphone remains off
    // until the researcher activates the voice orb.
    connectLiveKit().catch(handleConnectError);
})();
