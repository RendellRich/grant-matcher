import { render } from "preact";
import "@fontsource-variable/public-sans";
import "@fontsource-variable/source-serif-4";
import "./styles.css";
import { App } from "./app";

render(<App />, document.getElementById("app")!);
