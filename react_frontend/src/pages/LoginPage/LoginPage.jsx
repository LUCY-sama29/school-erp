import { useState } from "react";
import "./LoginPage.css";

import BackgroundParticles from "./components/BackgroundParticles/BackgroundParticles";
import Characters from "./components/Characters/Characters";
import LoginForm from "./components/LoginForm/LoginForm";

export default function LoginPage() {
  // emotion can be:
  // idle | happy | password | error | success
  const [emotion, setEmotion] = useState("idle");
  const [showPassword, setShowPassword] = useState(false);

  return (
    <div className="login-page">
      {/* Floating background */}
      <BackgroundParticles />

      {/* Animated characters */}
      <Characters
        emotion={emotion}
        showPassword={showPassword}
      />

      {/* Login form */}
      <LoginForm
        emotion={emotion}
        setEmotion={setEmotion}
        showPassword={showPassword}
        setShowPassword={setShowPassword}
      />
    </div>
  );
}
