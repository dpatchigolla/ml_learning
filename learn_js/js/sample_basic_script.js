// Sample js code to test functionality and syntax

function multiply() {
    var num = prompt('Enter number1:', 10);
    var num2 = prompt('Enter number2:', 2);
    var ans = num * num2;
    document.getElementById("demo").innerHTML = ans
    //print(ans)
}

Math.floor(3.2)




function resizeImg(img_path, ref_img_path) {
    var img = new SimpleImage(img_path);
    var ref_img = new SimpleImage(ref_img_path);
    var img_width = img.getWidth();
    var img_height = img.getHeight();
    var ref_img_width = ref_img.getWidth();
    var ref_img_height = ref_img.getHeight();
    var rescale_x = img_width/ref_img_width;
    var rescale_y = img_height/ref_img_height;
    var outputImg = new SimpleImage(ref_img_width, ref_img_height);
    for (var px of ref_img.values()){
        var x = px.getX();
        var y = px.getY();
        var x_orig = Math.floor(x * rescale_x);
        var y_orig = Math.floor(y * rescale_y);
        outputImg.setPixel(x,y, img.getPixel(x_orig, y_orig));

    }
    return outputImg
}

print(resizeImg('matrix.jpeg', 'trump_greenscreen.jpg'))

function greenScreen(fg_path, bg_path){
    var fgImg = new SimpleImage(fg_path);
    var bgImg = new SimpleImage(bg_path);
    if (bgImg.getWidth() != fgImg.getWidth() || bgImg.getHeight() != fgImg.getHeight()) {
        var bgImg = new resizeImg(bg_path, fg_path)
    }
    print(fgImg)
    print(bgImg)

    var outputImg = new SimpleImage(fgImg.getWidth(), fgImg.getHeight());

    for (var px of fgImg.values()){
        var x= px.getX()
        var y = px.getY()
        //if (px.getGreen()>=200 && px.getRed()<=10 && px.getBlue()<=10) {
        if (px.getGreen()>  px.getRed() + px.getBlue()) {
            var replacePix = bgImg.getPixel(x,y)
            outputImg.setPixel(x,y, replacePix)
        }
        else{
            outputImg.setPixel(x,y, px);}
    }
    print(outputImg)
}