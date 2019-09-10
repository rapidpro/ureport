# wires in any facebook shares on the page
$(->
  $(".facebook-share").on("click", ->
    shareURL = $(this).data("url")
    url = "https://www.facebook.com/sharer/sharer.php?u=" + shareURL
    FB.ui({
        method: "share"
        href: url
      },
      (response) ->
        console.log(response);
    )
  )
)