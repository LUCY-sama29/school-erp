import { useEffect, useRef } from "react";
import gsap from "gsap";

export default function Eyes({ showPassword }) {
  const eyesRef = useRef([]);

  /* Cursor follow */
  useEffect(() => {
    const move = (e) => {
      if (showPassword) return;

      const x = (e.clientX / window.innerWidth - 0.5) * 10;
      const y = (e.clientY / window.innerHeight - 0.5) * 10;

      gsap.to(eyesRef.current, {
        x,
        y,
        duration: 0.3,
        ease: "power2.out",
      });
    };

    window.addEventListener("mousemove", move);
    return () => window.removeEventListener("mousemove", move);
  }, [showPassword]);

  /* Blinking */
  useEffect(() => {
    const blink = setInterval(() => {
      gsap.to(eyesRef.current, { scaleY: 0.1, duration: 0.1 });
      gsap.to(eyesRef.current, { scaleY: 1, delay: 0.15 });
    }, 3000);

    return () => clearInterval(blink);
  }, []);

  return (
    <>
      <div className="eye left" ref={(el) => eyesRef.current[0] = el} />
      <div className="eye right" ref={(el) => eyesRef.current[1] = el} />
    </>
  );
}
