// author: amirhossein kiani
// keeping things simple...
// tag cloud and png generation from http://www.jasondavies.com/wordcloud
var cachedWords;
var cachedProcessed;

$("#select-db").click(function () {
    $("#file-browser").fileupload({
        dataType: 'json',
        done: function (e, data) {
            var response = JSON.parse(data.xhr().response);
            if (response.success != undefined) {
                var id = response.success;
                $.getJSON("process?db=" + id, function (data) {
                    drawCloud(data);
                    $("#upload-progress").hide();
                });
            } else {
                if (response.error != undefined) {
                    $("#upload-status").text(response.error);
                } else {
                    $("#upload-status").text(JSON.stringfy(response));
                }
            }
        },
        fail: function (e, data) {
            $("#upload-status").text(JSON.stringfy(data.xhr().response));
        },
        start: function () {
            $("#save-image").hide();
            $("#upload-status").text("");
            $("#upload-progress").show();
        },
        progressall: function (e, data) {
            var progress = parseInt(data.loaded / data.total * 100, 10);
            $('#upload-progress .progress-bar').css('width', progress + '%');
        }
    });

    $("#file-browser").click();
});

var resetSize = function() {
    width = Math.max($(".main").width(), 300), height = Math.max($(window).height(), 200);    
}

var fill = d3.scale.category20();
resetSize();

function drawCloud(words) {
    cachedWords = words;
    var min = Number.MAX_VALUE;
    var max = Number.MIN_VALUE;
    var words = words.map(function (d) {
        var text = d[0];
        var size = d[1];

        if (size < min) {
            min = size
        }

        if (size > max) {
            max = size;
        }

        return {
            text: text,
            size: size
        };
    });

    var sizeFunction = d3.scale.log().domain([min, max]).range([width/50, width/10]);

    d3.layout.cloud().size([width, height]).words(words).padding(0).rotate(

    function () {
        return ~~ (Math.random() * 2) * 90;
    }).font("Impact").fontSize(function (d) {
        return sizeFunction(d.size);
    }).on("end", draw).start();
    
    $("#save-image").show();
}

$(window).resize(function () {
    if (cachedWords != undefined) {
	resetSize();
        drawCloud(cachedWords);
    }
})

function draw(words) {
    cachedProcessed = words;
    $("#tag-cloud svg").remove();
    d3.select("#tag-cloud").append("svg").attr("width", width).attr("height", height).append("g").attr("transform", "translate(" + width / 2 + "," + height / 2 + ")").selectAll("text").data(words).enter().append("text").style("font-size", function (d) {
        return d.size + "px";
    }).style("font-family", "Impact").style("fill", function (d, i) {
        return fill(i);
    }).attr("text-anchor", "middle").attr("transform", function (d) {
        return "translate(" + [d.x, d.y] + ")rotate(" + d.rotate + ")";
    }).text(function (d) {
        return d.text;
    });
}

//Converts a given word cloud to image/png.
function downloadPNG() {
    var words = cachedProcessed;
    var canvas = document.createElement("canvas"),
        c = canvas.getContext("2d");
    canvas.width = width;
    canvas.height = height;
    c.translate(width >> 1, height >> 1);
    words.forEach(function (word, i) {
        c.save();
        c.translate(word.x, word.y);
        c.rotate(word.rotate * Math.PI / 180);
        c.textAlign = "center";
        c.fillStyle = fill(word.text.toLowerCase());
        c.font = word.size + "px " + word.font;
        c.fillText(word.text, 0, 0);
        c.restore();
    });
    
    c.fillStyle = "gray";
    c.font = "14px Helvetica";
    c.fillText("http://t.kiani.me", width/2-150, height/2 - 30);
    
    d3.select(this).attr("href", canvas.toDataURL("image/png"));
}

$("#save-image").click(downloadPNG);
$("#show-tutorial").click(function() {
    if($("#show-tutorial").text() != "hide tutorial"){
	$("#show-tutorial").text("hide tutorial");
    }else{
	$("#show-tutorial").text("show tutorial");
    }
	
    $("#tutorial").toggle();
});