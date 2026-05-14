$(".category_list > li:has(ul) > a").each(function () {
  $(this).removeAttr("href");
  $(this).prepend('<i class="ph-playlist-bold"></i>');
  $(".sub_category_list").hide();
  $(this).click(function () {
    $(this).next().slideToggle(200);
    $(".sub_category_list").not($(this).next()).slideUp(200);
  });
});
$(".tagTrail").each(function () {
  var tag = $(this).html().replace(/,/g, "");
  $(this).html(tag);
});
$(".category_list > li:not(:has(ul)) > a").each(function () {
  $(this).prepend('<i class="ph-list-bold"></i>');
});
$(".list_rep .index").each(function () {
  $(this).attr("class", $("#listStyle").attr("class"));
});
$(".article").each(function () {
  $(this).find(".container_postbtn").prependTo($(this).prev().find(".info_text .article_bottom"));
});
$(".notice_label").each(function () {
  $(this).click(function () {
    $(this).next().fadeIn(300);
    $(".notice_bg").fadeIn(300);
  });
});
$(".notice_inner .close").click(function () {
  $(".notice_inner, .notice_bg").fadeOut(300);
});
$(".cmt_toggle").click(function () {
  $(this).next("#comment").slideToggle(300);
});
$(".guest_secret.hiddenComment .cmtName, .rp_secret.hiddenComment .cmtName").html("<a>비밀손님</a>");
$(".footer .toggle").click(function () {
  $("#sidebar").addClass("open");
  $(".sidebar-bg").fadeIn(400);
});
$(".sidebar-bg").click(function () {
  $("#sidebar").removeClass("open");
  $(this).fadeOut(400);
});
$(function () {
  function screenw(max_width) {
    if (max_width.matches) {
      $(".admin").insertBefore(".article");
    }
  }
  var max_width = window.matchMedia("(max-width: 470px)");
  screenw(max_width);
  max_width.addListener(screenw);
});
