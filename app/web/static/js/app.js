"use strict";

/*
 * VoiceLab
 * Global browser-side application helpers.
 *
 * Main voice WebSocket logic lives in workspace.html because the
 * workspace owns the active voice session.
 *
 * This file provides small shared helpers for the three-screen MVP.
 */


/* ================================================================
   VoiceLab namespace
   ================================================================ */

window.VoiceLab = window.VoiceLab || {};


/* ================================================================
   Session helpers
   ================================================================ */

VoiceLab.getSessionId = function () {
    const params =
        new URLSearchParams(
            window.location.search
        );

    return params.get("session_id");
};


VoiceLab.requireSessionId = function () {
    const sessionId =
        VoiceLab.getSessionId();

    if (!sessionId) {
        window.location.href = "/";
        return null;
    }

    return sessionId;
};


VoiceLab.sessionUrl = function (
    path,
    sessionId
) {
    const separator =
        path.includes("?")
            ? "&"
            : "?";

    return (
        path +
        separator +
        "session_id=" +
        encodeURIComponent(
            sessionId
        )
    );
};


/* ================================================================
   WebSocket helpers
   ================================================================ */

VoiceLab.getWebSocketUrl = function (
    path
) {
    const protocol =
        window.location.protocol === "https:"
            ? "wss:"
            : "ws:";

    return (
        protocol +
        "//" +
        window.location.host +
        path
    );
};


VoiceLab.createVoiceWebSocket = function (
    sessionId
) {
    if (!sessionId) {
        throw new Error(
            "A session_id is required."
        );
    }

    const path =
        "/ws/voice/" +
        encodeURIComponent(
            sessionId
        );

    return new WebSocket(
        VoiceLab.getWebSocketUrl(
            path
        )
    );
};


/* ================================================================
   Safe JSON
   ================================================================ */

VoiceLab.parseJSON = function (
    value
) {
    try {
        return JSON.parse(
            value
        );
    } catch {
        return null;
    }
};


/* ================================================================
   HTML escaping
   ================================================================ */

VoiceLab.escapeHtml = function (
    value
) {
    const element =
        document.createElement(
            "div"
        );

    element.textContent =
        String(value ?? "");

    return element.innerHTML;
};


/* ================================================================
   Number formatting
   ================================================================ */

VoiceLab.formatNumber = function (
    value
) {
    if (
        typeof value !== "number" ||
        !Number.isFinite(value)
    ) {
        return String(value);
    }

    if (
        Math.abs(value) < 1e-10
    ) {
        return "0";
    }

    return Number(
        value.toFixed(6)
    ).toString();
};


/* ================================================================
   Matrix formatting
   ================================================================ */

VoiceLab.formatMatrix = function (
    matrix
) {
    if (
        !Array.isArray(matrix)
    ) {
        return "";
    }

    return matrix
        .map(
            row =>
                row
                    .map(
                        VoiceLab.formatNumber
                    )
                    .join("  ")
        )
        .join("\n");
};


/* ================================================================
   API helpers
   ================================================================ */

VoiceLab.api = async function (
    url,
    options = {}
) {
    const response =
        await fetch(
            url,
            {
                ...options,
                headers: {
                    "Content-Type":
                        "application/json",
                    ...(options.headers || {})
                }
            }
        );

    let data = null;

    const contentType =
        response.headers.get(
            "content-type"
        ) || "";

    if (
        contentType.includes(
            "application/json"
        )
    ) {
        data =
            await response.json();
    } else {
        data =
            await response.text();
    }

    if (!response.ok) {
        const message =
            typeof data === "object" &&
            data?.detail
                ? data.detail
                : "Request failed.";

        throw new Error(
            message
        );
    }

    return data;
};


VoiceLab.getSessionState = async function (
    sessionId
) {
    return VoiceLab.api(
        "/api/sessions/" +
        encodeURIComponent(
            sessionId
        )
    );
};


/* ================================================================
   Navigation
   ================================================================ */

VoiceLab.goToWorkspace = function (
    sessionId
) {
    window.location.href =
        VoiceLab.sessionUrl(
            "/workspace",
            sessionId
        );
};


VoiceLab.goToResult = function (
    sessionId
) {
    window.location.href =
        VoiceLab.sessionUrl(
            "/result",
            sessionId
        );
};


/* ================================================================
   Generic event emitter
   ================================================================ */

VoiceLab.createEventEmitter =
    function () {
        const listeners =
            new Map();

        return {
            on(
                eventName,
                callback
            ) {
                if (
                    !listeners.has(
                        eventName
                    )
                ) {
                    listeners.set(
                        eventName,
                        new Set()
                    );
                }

                listeners
                    .get(eventName)
                    .add(callback);

                return () => {
                    listeners
                        .get(eventName)
                        ?.delete(
                            callback
                        );
                };
            },

            emit(
                eventName,
                payload
            ) {
                const callbacks =
                    listeners.get(
                        eventName
                    );

                if (!callbacks) {
                    return;
                }

                callbacks.forEach(
                    callback => {
                        try {
                            callback(
                                payload
                            );
                        } catch (
                            error
                        ) {
                            console.error(
                                "VoiceLab event error:",
                                error
                            );
                        }
                    }
                );
            },

            clear() {
                listeners.clear();
            }
        };
    };


/* ================================================================
   Audio helpers
   ================================================================ */

VoiceLab.floatToPCM16 =
    function (input) {
        const output =
            new Int16Array(
                input.length
            );

        for (
            let i = 0;
            i < input.length;
            i += 1
        ) {
            const sample =
                Math.max(
                    -1,
                    Math.min(
                        1,
                        input[i]
                    )
                );

            output[i] =
                sample < 0
                    ? sample * 0x8000
                    : sample * 0x7fff;
        }

        return output;
    };


VoiceLab.arrayBufferToBase64 =
    function (buffer) {
        const bytes =
            new Uint8Array(
                buffer
            );

        let binary = "";

        const chunkSize =
            0x8000;

        for (
            let i = 0;
            i < bytes.length;
            i += chunkSize
        ) {
            const chunk =
                bytes.subarray(
                    i,
                    Math.min(
                        i + chunkSize,
                        bytes.length
                    )
                );

            binary +=
                String.fromCharCode(
                    ...chunk
                );
        }

        return btoa(
            binary
        );
    };


VoiceLab.base64ToArrayBuffer =
    function (base64) {
        const binary =
            atob(base64);

        const bytes =
            new Uint8Array(
                binary.length
            );

        for (
            let i = 0;
            i < binary.length;
            i += 1
        ) {
            bytes[i] =
                binary.charCodeAt(i);
        }

        return bytes.buffer;
    };


/* ================================================================
   Audio playback helper
   ================================================================ */

VoiceLab.createAudioPlayer =
    function () {
        let audioContext = null;
        let nextStartTime = 0;

        function ensureContext() {
            if (!audioContext) {
                audioContext =
                    new (
                        window.AudioContext ||
                        window.webkitAudioContext
                    )({
                        sampleRate: 24000
                    });
            }

            return audioContext;
        }

        async function playPCM16(
            arrayBuffer
        ) {
            const context =
                ensureContext();

            if (
                context.state ===
                "suspended"
            ) {
                await context.resume();
            }

            const pcm =
                new Int16Array(
                    arrayBuffer
                );

            const audioBuffer =
                context.createBuffer(
                    1,
                    pcm.length,
                    24000
                );

            const channel =
                audioBuffer.getChannelData(
                    0
                );

            for (
                let i = 0;
                i < pcm.length;
                i += 1
            ) {
                channel[i] =
                    pcm[i] < 0
                        ? pcm[i] / 0x8000
                        : pcm[i] / 0x7fff;
            }

            const source =
                context.createBufferSource();

            source.buffer =
                audioBuffer;

            source.connect(
                context.destination
            );

            const startTime =
                Math.max(
                    context.currentTime,
                    nextStartTime
                );

            source.start(
                startTime
            );

            nextStartTime =
                startTime +
                audioBuffer.duration;
        }

        function close() {
            if (audioContext) {
                audioContext
                    .close()
                    .catch(
                        () => {}
                    );

                audioContext = null;
            }

            nextStartTime = 0;
        }

        return {
            playPCM16,
            close
        };
    };


/* ================================================================
   DOM helpers
   ================================================================ */

VoiceLab.show = function (
    element
) {
    if (element) {
        element.classList.remove(
            "hidden"
        );
    }
};


VoiceLab.hide = function (
    element
) {
    if (element) {
        element.classList.add(
            "hidden"
        );
    }
};


VoiceLab.setText = function (
    element,
    value
) {
    if (element) {
        element.textContent =
            value ?? "";
    }
};


/* ================================================================
   Browser lifecycle
   ================================================================ */

VoiceLab.onPageExit =
    function (callback) {
        window.addEventListener(
            "beforeunload",
            callback
        );

        window.addEventListener(
            "pagehide",
            callback
        );
    };


/* ================================================================
   Debug helper
   ================================================================ */

VoiceLab.debug =
    function (...args) {
        if (
            window.location.hostname ===
            "localhost"
        ) {
            console.debug(
                "[VoiceLab]",
                ...args
            );
        }
    };