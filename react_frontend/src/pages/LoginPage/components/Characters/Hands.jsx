import { useEffect, useRef } from "react";
import gsap from "gsap";

export default function Hands({ emotion, showPassword }) {
  const handsRef = useRef();

  useEffect(() => {
    if (emotion === "password" || showPassword) {
      gsap.to(handsRef.current, { y: -40, duration: 0.4 });
    } else {
      gsap.to(handsRef.current, { y: 0, duration: 0.4 });
    }
  }, [emotion, showPassword]);

  return <div className="hands" ref={handsRef} />;
}
