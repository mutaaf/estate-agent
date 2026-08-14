import axios from "axios";

export async function charge(order: Order) {
  return axios.post(`${process.env.PAYMENTS_API_URL}/v2/charge`, order);
}
