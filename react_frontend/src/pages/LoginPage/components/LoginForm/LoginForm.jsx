import "./LoginForm.css";

export default function LoginForm({
  emotion,
  setEmotion,
  showPassword,
  setShowPassword
}) {

const handleSubmit = async (e) => {
  e.preventDefault();
  setEmotion("idle");

  const form = e.target;
  const username = form.username.value;
  const password = form.password.value;

  try {
    const res = await fetch("http://127.0.0.1:5000/api/login", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      credentials: "include", // VERY IMPORTANT
      body: JSON.stringify({ username, password }),
    });

    const data = await res.json();

    if (data.success) {
      setEmotion("success");
      // later → redirect to dashboard
    } else {
      setEmotion("error");
    }
  } catch (err) {
    setEmotion("error");
  }
};


  return (
    <div className="login-form-wrapper">
      <div className="login-card">
        <h2>Welcome back</h2>

        <form onSubmit={handleSubmit}>
          {/* USERNAME */}
          <label>Username</label>
          <input
              name="username"
              type="text"
              onFocus={() => setEmotion("happy")}
              onBlur={() => setEmotion("idle")}
              required
            />

          {/* PASSWORD */}
          <label>Password</label>
          <input
              name="password"
              type={showPassword ? "text" : "password"}
              onFocus={() => setEmotion("password")}
              onBlur={() => setEmotion("idle")}
              required
            />

          {/* SHOW PASSWORD */}
          <div className="show-password">
            <input
              type="checkbox"
              checked={showPassword}
              onChange={(e) => setShowPassword(e.target.checked)}
            />
            <span>Show password</span>
          </div>

          <button type="submit">
            Login
          </button>
        </form>

        {/* ERROR MESSAGE */}
        {emotion === "error" && (
          <p className="error-text">Invalid username or password</p>
        )}
      </div>
    </div>
  );
}
