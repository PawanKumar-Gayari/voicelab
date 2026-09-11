/* VoiceLab LiveKit browser transport.
 * This intentionally contains no science logic. workspace.js remains the UI/state layer.
 */

window.VoiceLabLiveKit = (() => {
  let room = null;

  async function connect({ url, token, onTrack, onDisconnected } = {}) {
    if (!window.LivekitClient) {
      throw new Error("LiveKit browser SDK is not loaded.");
    }

    room = new LivekitClient.Room({
      adaptiveStream: true,
      dynacast: true,
    });

    room.on(LivekitClient.RoomEvent.TrackSubscribed, (track) => {
      if (track.kind === LivekitClient.Track.Kind.Audio) {
        const element = track.attach();
        element.autoplay = true;
        element.playsInline = true;
        document.body.appendChild(element);
      }
      if (typeof onTrack === "function") onTrack(track);
    });

    room.on(LivekitClient.RoomEvent.Disconnected, (reason) => {
      if (typeof onDisconnected === "function") onDisconnected(reason);
    });

    room.on(LivekitClient.RoomEvent.AudioPlaybackStatusChanged, () => {
      if (!room.canPlaybackAudio) {
        console.warn("[VoiceLab] Browser is blocking LiveKit audio playback until a user gesture.");
      }
    });

    room.on(LivekitClient.RoomEvent.MediaDevicesError, (error) => {
      console.error("[VoiceLab] LiveKit media device error:", error);
    });

    await room.connect(url, token);
    // Keep the microphone disabled until the researcher explicitly
    // activates the voice orb. Connecting to LiveKit must not prompt for
    // microphone permission or start publishing audio.
    return room;
  }

  async function startAudio() {
    if (!room) return false;

    if (typeof room.startAudio === "function") {
      await room.startAudio();
      return true;
    }

    // Compatibility fallback for older client builds.
    const audioElements = document.querySelectorAll("audio");
    for (const element of audioElements) {
      try {
        await element.play();
      } catch (_) {}
    }
    return true;
  }

  async function disconnect() {
    if (room) {
      await room.disconnect();
      room = null;
    }
  }

  return { connect, startAudio, disconnect, getRoom: () => room };
})();
