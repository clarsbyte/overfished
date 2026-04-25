import { AnimatePresence, motion } from "framer-motion";
import { useEffect, useState } from "react";

type Stage = "init" | "connect" | "reveal" | "done";
const SERVICES = ["GFW", "ELEVENLABS", "BLAND", "CLOUDINARY"];

interface Props {
  onComplete: () => void;
}

export function IntroSequence({ onComplete }: Props) {
  const [stage, setStage] = useState<Stage>("init");
  const [skipped, setSkipped] = useState(false);

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setSkipped(true);
        onComplete();
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [onComplete]);

  useEffect(() => {
    if (skipped) return;
    const timers = [
      setTimeout(() => setStage("connect"), 300),
      setTimeout(() => setStage("reveal"), 800),
      setTimeout(() => setStage("done"), 1000),
      setTimeout(() => onComplete(), 1200),
    ];
    return () => timers.forEach(clearTimeout);
  }, [skipped, onComplete]);

  return (
    <AnimatePresence>
      {!skipped && stage !== "done" && (
        <motion.div
          initial={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.5 }}
          className="fixed inset-0 z-[9999] bg-[#06080f] flex items-center justify-center overflow-hidden"
        >
          <div
            className="absolute inset-0 opacity-30"
            style={{
              backgroundImage:
                "linear-gradient(rgba(0,212,255,0.08) 1px, transparent 1px), linear-gradient(90deg, rgba(0,212,255,0.08) 1px, transparent 1px)",
              backgroundSize: "40px 40px",
            }}
          />

          <motion.div
            className="absolute left-0 right-0 h-[2px] bg-cyan-400/70 shadow-[0_0_12px_2px_rgba(0,212,255,0.6)] z-20"
            initial={{ top: "-2px" }}
            animate={{ top: "100%" }}
            transition={{
              duration: 1.4,
              ease: "linear",
              repeat: stage === "init" || stage === "connect" ? Infinity : 0,
            }}
          />

          {stage !== "init" && (
            <motion.div
              initial={{ opacity: 0, scale: 0.6 }}
              animate={{ opacity: 0.18, scale: 1 }}
              transition={{ duration: 1.2, ease: [0.16, 1, 0.3, 1] }}
              className="absolute w-[480px] h-[480px] rounded-full"
              style={{
                background:
                  "radial-gradient(circle at 35% 35%, #1a3a6b 0%, #0a2540 40%, transparent 70%)",
                boxShadow: "0 0 120px 20px rgba(0,212,255,0.12)",
              }}
            />
          )}

          <div className="relative z-10 font-mono text-cyan-400 text-center px-4">
            <TypedLine text="INITIALIZING ORBITAL SURVEILLANCE" />

            {(stage === "connect" || stage === "reveal") && (
              <motion.div
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.4, delay: 0.2 }}
                className="mt-8"
              >
                <div className="text-[10px] tracking-[0.4em] text-cyan-400/60 mb-3">
                  CONNECTING TO
                </div>
                <div className="flex gap-3 justify-center flex-wrap">
                  {SERVICES.map((s, i) => (
                    <ServicePill key={s} name={s} delay={i * 0.18} />
                  ))}
                </div>
              </motion.div>
            )}

            {stage === "reveal" && (
              <motion.div
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                transition={{ duration: 0.4, delay: 0.4 }}
                className="mt-8 text-[10px] tracking-[0.5em] text-cyan-300"
              >
                READY
              </motion.div>
            )}
          </div>

          <div className="absolute bottom-6 right-6 text-[10px] font-mono tracking-[0.3em] text-cyan-400/30">
            ESC TO SKIP
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}

function TypedLine({ text }: { text: string }) {
  const [idx, setIdx] = useState(0);
  useEffect(() => {
    if (idx < text.length) {
      const t = setTimeout(() => setIdx(idx + 1), 28);
      return () => clearTimeout(t);
    }
  }, [idx, text.length]);
  return (
    <div className="text-sm tracking-[0.4em] text-cyan-300">
      {text.slice(0, idx)}
      <span className="inline-block w-[2px] h-4 align-middle ml-1 bg-cyan-400 animate-pulse" />
    </div>
  );
}

function ServicePill({ name, delay }: { name: string; delay: number }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, delay }}
      className="flex items-center gap-2 px-3 py-1.5 border border-cyan-400/20 rounded bg-cyan-400/5"
    >
      <motion.span
        initial={{ backgroundColor: "#475569" }}
        animate={{ backgroundColor: "#10b981" }}
        transition={{ duration: 0.3, delay: delay + 0.25 }}
        className="w-1.5 h-1.5 rounded-full shadow-[0_0_6px_rgba(16,185,129,0.6)]"
      />
      <span className="text-[10px] tracking-[0.2em]">{name}</span>
    </motion.div>
  );
}
