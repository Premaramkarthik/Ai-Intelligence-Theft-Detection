import type { ReactNode, Ref } from "react";

interface VideoPlayerProps {
  videoRef: Ref<HTMLVideoElement>;
  overlay?: ReactNode;
}

export function VideoPlayer({ videoRef, overlay }: VideoPlayerProps) {
  return (
    <div className="relative overflow-hidden rounded-[28px] border border-white/10 bg-slate-950 shadow-[0_30px_120px_rgba(0,0,0,0.45)] transition-all duration-500 ease-out">
      <div className="aspect-video bg-[radial-gradient(circle_at_top,_rgba(59,130,246,0.18),_transparent_52%),linear-gradient(160deg,_#0f172a,_#020617)]">
        <video
          ref={videoRef}
          className="size-full object-contain bg-black transition-opacity duration-500 ease-out"
          autoPlay
          playsInline
          muted
          controls={false}
        />
      </div>
      {overlay}
    </div>
  );
}
