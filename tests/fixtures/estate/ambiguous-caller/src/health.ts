import axios from "axios";

export const ping = () => axios.get("/internal/metrics");
