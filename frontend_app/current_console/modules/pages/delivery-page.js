(function registerDeliveryPage(global) {
  "use strict";

  global.PowerRAGPages.register({ id: "delivery", mode: "rag", title: "可信交付" });
  let refresh = null;
  global.addEventListener("powerrag:page-enter", (event) => {
    if (event.detail?.id === "delivery" && refresh) {
      Promise.resolve(refresh({ silent: true })).catch((error) => console.error(error));
    }
  });
  global.PowerRAGDeliveryPage = Object.freeze({
    mount(controller) {
      refresh = controller?.refresh || null;
    },
  });
})(globalThis);
