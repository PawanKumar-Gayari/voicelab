/*
 * mic-capture-processor.js
 *
 * AudioWorkletProcessor used by workspace.html to capture microphone
 * audio for VoiceLab.
 *
 * WHY THIS EXISTS
 * ----------------
 * The previous implementation used ScriptProcessorNode, which runs
 * its callback on the MAIN thread. Any main-thread work happening at
 * the same time (DOM updates from research-state rendering, JSON
 * parsing of incoming WebSocket events, garbage collection, etc.)
 * could delay or skip an audio callback, producing gaps/stutter in
 * the outgoing microphone stream.
 *
 * AudioWorkletProcessor code runs on a dedicated, high-priority audio
 * rendering thread that is isolated from the main thread, so it keeps
 * producing audio callbacks on schedule regardless of what the page
 * is doing. This is the standard fix recommended by the Web Audio
 * spec for exactly this class of problem.
 *
 * WHAT IT DOES
 * ------------
 * - Receives 128-frame mono Float32 blocks from the microphone.
 * - Resamples them (linear interpolation, with fractional-position
 *   state carried across blocks so there is no discontinuity at
 *   block boundaries) down to the target output sample rate
 *   (24 kHz, to match the existing AssemblyAI contract).
 * - Converts to PCM16.
 * - Buffers into small fixed-size chunks (chunkSamples, default 480
 *   samples = 20ms @ 24kHz) and posts each chunk to the main thread
 *   as a transferable ArrayBuffer.
 *
 * The main thread (workspace.html) is responsible only for base64
 * encoding + JSON-wrapping + the WebSocket send + backpressure check,
 * which is comparatively cheap. This keeps the expensive per-sample
 * work off the main thread entirely.
 *
 * This file does NOT talk to the WebSocket directly — AudioWorklets
 * cannot safely hold a WebSocket connection, and keeping networking
 * on the main thread means the existing reconnect/backpressure logic
 * in workspace.html did not need to change.
 */

class MicCaptureProcessor extends AudioWorkletProcessor {

    constructor(options) {

        super();

        const opts =
            (options && options.processorOptions) || {};

        // `sampleRate` is a global provided by the
        // AudioWorkletGlobalScope equal to the owning AudioContext's
        // sample rate. Used as a safe default if the caller didn't
        // pass one explicitly.
        this.inputSampleRate =
            opts.inputSampleRate || sampleRate;

        this.outputSampleRate =
            opts.outputSampleRate || 24000;

        this.chunkSamples =
            opts.chunkSamples || 480;

        this.ratio =
            this.inputSampleRate / this.outputSampleRate;

        // Leftover input samples kept across process() calls so the
        // linear interpolation has no discontinuity at block edges.
        this.inputCarry = new Float32Array(0);

        // Fractional position within the (carry + new) buffer.
        this.position = 0;

        this.outBuffer = new Int16Array(this.chunkSamples);
        this.outIndex = 0;

        this.errored = false;
    }

    process(inputs) {

        // Returning false would permanently stop this processor.
        // Prefer to keep it alive and just skip bad frames, and
        // surface a single console warning instead of throwing
        // repeatedly.
        try {

            const input = inputs[0];

            if (!input || input.length === 0) {
                return true;
            }

            const channelData = input[0];

            if (!channelData || channelData.length === 0) {
                return true;
            }

            let combined;

            if (this.inputCarry.length > 0) {

                combined =
                    new Float32Array(
                        this.inputCarry.length + channelData.length
                    );

                combined.set(this.inputCarry, 0);
                combined.set(channelData, this.inputCarry.length);

            }
            else {

                combined = channelData;
            }

            if (this.ratio === 1) {

                this.appendOutput(combined);

                this.inputCarry = new Float32Array(0);

                return true;
            }

            const outputSamples = [];

            let pos = this.position;

            while (true) {

                const left = Math.floor(pos);
                const right = left + 1;

                if (right >= combined.length) {
                    break;
                }

                const fraction = pos - left;

                const sample =
                    combined[left] * (1 - fraction) +
                    combined[right] * fraction;

                outputSamples.push(sample);

                pos += this.ratio;
            }

            const consumedIndex = Math.floor(pos);

            this.inputCarry = combined.slice(consumedIndex);
            this.position = pos - consumedIndex;

            if (outputSamples.length > 0) {

                this.appendOutput(
                    Float32Array.from(outputSamples)
                );
            }

            return true;

        }
        catch (error) {

            if (!this.errored) {

                this.errored = true;

                // eslint-disable-next-line no-console
                console.error(
                    "mic-capture-processor error:",
                    error
                );
            }

            // Keep the processor alive; a single bad block should
            // not silently kill microphone capture for the rest of
            // the session.
            return true;
        }
    }

    appendOutput(floatSamples) {

        for (let i = 0; i < floatSamples.length; i += 1) {

            const sample =
                Math.max(-1, Math.min(1, floatSamples[i]));

            this.outBuffer[this.outIndex] =
                sample < 0
                    ? sample * 32768
                    : sample * 32767;

            this.outIndex += 1;

            if (this.outIndex >= this.chunkSamples) {

                this.flush();
            }
        }
    }

    flush() {

        if (this.outIndex === 0) {
            return;
        }

        // Slice to exactly what was filled, then transfer the
        // underlying buffer to avoid a structured-clone copy.
        const filled =
            this.outIndex === this.chunkSamples
                ? this.outBuffer
                : this.outBuffer.slice(0, this.outIndex);

        const transferBuffer = filled.buffer;

        this.port.postMessage(transferBuffer, [transferBuffer]);

        this.outBuffer = new Int16Array(this.chunkSamples);
        this.outIndex = 0;
    }
}

registerProcessor("mic-capture-processor", MicCaptureProcessor);
