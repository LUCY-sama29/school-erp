import "./Characters.css";
import Eyes from "./Eyes";
import Mouth from "./Mouth";
import Hands from "./Hands";

export default function Characters({ emotion, showPassword }) {
  return (
    <div className="characters">
      {/* Orange circle (decorative) */}
      <div className="shape orange" />

      {/* Blue character */}
      <div className="shape blue face">
        <Hands emotion={emotion} showPassword={showPassword} />
        <Eyes emotion={emotion} showPassword={showPassword} />
        <Mouth emotion={emotion} />
      </div>

      {/* Black character */}
      <div className="shape black face">
        <Eyes emotion={emotion} showPassword={showPassword} />
        <Mouth emotion={emotion} />
      </div>
    </div>
  );
}
