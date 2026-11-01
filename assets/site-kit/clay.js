/* ============================================================
   clay.js —— 全站黏土微动效
   包含：按钮按压 Q 弹、卡片指针倾斜、滚动进场、点击迸出小圆点
   全部尊重系统"减少动态"设置
   ============================================================ */
(function () {
  "use strict";

  var reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  var finePointer = window.matchMedia("(pointer: fine)").matches;

  /* ---------- 1. 按压 Q 弹（按住缩小，松开回弹） ---------- */
  document.querySelectorAll(".clay-btn, .nav-link, .clay-icon, .chip").forEach(function (el) {
    el.addEventListener("pointerdown", function () {
      el.classList.add("pressed");
    });
    ["pointerup", "pointerleave", "pointercancel"].forEach(function (ev) {
      el.addEventListener(ev, function () {
        el.classList.remove("pressed");
      });
    });
  });

  if (reduceMotion) return;

  /* ---------- 2. 卡片跟随指针轻微 3D 倾斜（仅鼠标） ---------- */
  if (finePointer) {
    /* data-no-tilt：长文阅读卡（如听力练习正文）不跟随指针倾斜 */
    document.querySelectorAll(".clay-card:not([data-no-tilt])").forEach(function (card) {
      card.addEventListener("pointermove", function (e) {
        var r = card.getBoundingClientRect();
        var px = (e.clientX - r.left) / r.width - 0.5;
        var py = (e.clientY - r.top) / r.height - 0.5;
        card.style.transform =
          "translateY(-6px) rotateX(" + (-py * 6).toFixed(2) + "deg) rotateY(" + (px * 6).toFixed(2) + "deg)";
      });
      card.addEventListener("pointerleave", function () {
        card.style.transform = "";
      });
    });
  }

  /* ---------- 3. 滚动进场：一进入视口就 Q 弹弹出 ---------- */
  var io = new IntersectionObserver(function (entries) {
    entries.forEach(function (en) {
      if (en.isIntersecting) {
        en.target.classList.add("in");
        io.unobserve(en.target);
      }
    });
  }, { threshold: 0.12 });

  document.querySelectorAll(".pop").forEach(function (el) { io.observe(el); });

  /* ---------- 4. 点击主按钮时迸出黏土小圆点 ---------- */
  var PALETTE = ["#FF8A5E", "#FFD97E", "#7FD8AC", "#9ED4F2", "#C9B6F0", "#FFB3C7"];

  document.querySelectorAll(".clay-btn").forEach(function (btn) {
    btn.addEventListener("click", function (e) {
      burst(e.clientX, e.clientY, 9);
    });
  });

  function burst(x, y, n) {
    for (var i = 0; i < n; i++) {
      (function (idx) {              /* 闭包捕获本次的 dot，否则清理全指向最后一颗 */
        var dot = document.createElement("span");
        var size = 7 + Math.random() * 9;
        dot.style.cssText =
          "position:fixed;left:" + (x - size / 2) + "px;top:" + (y - size / 2) + "px;" +
          "width:" + size + "px;height:" + size + "px;border-radius:50%;" +
          "background:" + PALETTE[idx % PALETTE.length] + ";pointer-events:none;z-index:998;";
        document.body.appendChild(dot);
        var ang = Math.random() * Math.PI * 2;
        var dist = 46 + Math.random() * 60;
        var dx = Math.cos(ang) * dist;
        var dy = Math.sin(ang) * dist - 26;
        dot.animate(
          [
            { transform: "translate(0,0) scale(1)", opacity: 1 },
            { transform: "translate(" + dx + "px," + dy + "px) scale(.2)", opacity: 0 }
          ],
          { duration: 480 + Math.random() * 220, easing: "cubic-bezier(.16,.84,.44,1)" }
        ).onfinish = function () { dot.remove(); };
        setTimeout(function () { dot.remove(); }, 1200);   /* 兜底：页面不渲染时动画冻结，靠定时器清理 */
      })(i);
    }
  }

  /* ---------- 5. 页脚小鱼：戳一下摇摆 ---------- */
  var footerLogo = document.querySelector(".footer-logo");
  if (footerLogo) {
    footerLogo.addEventListener("click", function () {
      footerLogo.classList.remove("poked");
      void footerLogo.offsetWidth; /* 重置动画 */
      footerLogo.classList.add("poked");
    });
  }

  /* ---------- 6. 导航高亮当前页 ---------- */
  var page = document.body.dataset.page;
  if (page) {
    document.querySelectorAll(".nav-link[data-nav]").forEach(function (a) {
      if (a.dataset.nav === page) a.classList.add("active");
    });
  }
})();
