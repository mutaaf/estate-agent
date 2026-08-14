export async function charge(body: unknown) {
  return fetch(`${process.env.NEXT_PUBLIC_PAYMENTS_API_URL}/v2/charge`, {
    method: "POST", body: JSON.stringify(body),
  });
}
