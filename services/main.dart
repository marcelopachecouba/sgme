import 'package:flutter/material.dart';
import 'screens/escalas_screen.dart';

void main() {

  runApp(MyApp());

}

class MyApp extends StatelessWidget {

  @override
  Widget build(BuildContext context) {

    return MaterialApp(

      title: 'SGME',

      theme: ThemeData(
        primarySwatch: Colors.blue,
      ),

      home: EscalasScreen(),

    );

  }
}