export default {
  async fetch(request) {
    const destination = new URL("/index.html", request.url);
    return Response.redirect(destination, 302);
  },
};
